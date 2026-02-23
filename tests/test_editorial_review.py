import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from scripts.create_gossip_post import (
    BODY_MAX_LINES,
    HOOK_MAX_LINES,
    NewsItem,
    _build_subtle_parallax_blur_graph,
    _build_subtle_image_zoom_filters,
    build_editorial_pack_for_item,
    _is_valid_ai_cta,
    _plan_overlay_layout,
    _run_editorial_review_gate,
)


class EditorialReviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.item = NewsItem(
            source="contigo",
            feed_url="https://contigo.com.br/feed",
            title="Jonas critica atitude de rival e causa debate no BBB 26",
            link="https://example.com/materia",
            published="2026-02-23T12:00:00Z",
            image_url="https://example.com/image.jpg",
            description=(
                "No confessionario, Jonas acusou falta de convivencia e disse que a rival pediu para sair, "
                "o que acendeu nova discussao entre os participantes."
            ),
        )

    @patch("scripts.create_gossip_post._review_editorial_with_ai", return_value=(None, "test_disabled"))
    def test_review_gate_recovers_from_bad_text(self, _mock_ai):
        fields, review = _run_editorial_review_gate(
            self.item,
            hook="TEM UM DETALHE NESSA HISTORIA",
            headline="coisa aleatoria",
            body="texto sem contexto e com final quebrado e",
            cta="ISSO E VERDADE?",
        )

        self.assertTrue(review.get("local_ok_after"))
        self.assertTrue(fields["hook"])
        self.assertTrue(fields["body"])
        self.assertTrue(_is_valid_ai_cta(fields["cta"]))

    def test_overlay_layout_plan_limits_lines(self):
        layout = _plan_overlay_layout(
            "JONAS CRITICA RIVAL E BBB PEGA FOGO",
            "Jonas acusa falta de convivencia, diz que rival pediu para sair e a casa se divide apos o conflito no reality.",
        )

        self.assertLessEqual(len(layout["hook_lines"]), HOOK_MAX_LINES)
        self.assertLessEqual(len(layout["tarja_lines"]), BODY_MAX_LINES)
        self.assertGreater(layout["hook_font_size"], 0)
        self.assertGreater(layout["tarja_font_size"], 0)

    def test_overlay_layout_plan_preserves_full_body_text(self):
        body = (
            "Durante a temporada nos EUA, Virginia e Vini Jr. agendam jantar com Kim Kardashian e "
            "ampliam conexoes no circuito internacional."
        )
        layout = _plan_overlay_layout("VIRGINIA E VINI JR JANTAM COM KIM", body)

        rendered_body = " ".join(" ".join(layout["tarja_lines"]).split())
        self.assertEqual(rendered_body, " ".join(body.upper().split()))

    def test_subtle_image_filters_have_motion_without_geometric_zoom(self):
        filters = _build_subtle_image_zoom_filters(11.0, fps=30)
        joined = ",".join(filters)

        self.assertNotIn("zoompan=", joined)
        self.assertNotIn("crop=", joined)
        self.assertIn("eq=brightness='", joined)
        self.assertIn("sin(2*PI*t/", joined)
        self.assertIn("eval=frame", joined)

    def test_parallax_blur_graph_moves_only_background(self):
        graph = _build_subtle_parallax_blur_graph()

        self.assertIn("split=2[fgsrc][bgsrc]", graph)
        self.assertIn("boxblur=32:12", graph)
        self.assertIn("overlay=0:0:format=auto", graph)
        self.assertIn("x='trunc((in_w-1080)/2+26*sin(2*PI*t/10.8))'", graph)
        self.assertIn("y='trunc((in_h-1920)/2+16*sin(2*PI*t/13.2+0.7))'", graph)
        self.assertNotIn("zoompan=", graph)

    @patch("scripts.create_gossip_post._review_editorial_with_ai", return_value=(None, "test_disabled"))
    @patch(
        "scripts.create_gossip_post._summarize_news_text",
        return_value=(
            "JONAS APONTA ESTRATEGIA DE RIVAL NO BBB?\n"
            "Jonas critica escolha de rival e aumenta tensao no jogo.\n"
            "No confessionario, ele diz que a rival pediu para sair e a casa se divide com a acusacao.\n"
            "A fala repercutiu rapido e gerou discussao sobre postura no reality. O clima entre aliados ficou mais tenso.\n"
            "COMENTA O QUE ACHOU!"
        ),
    )
    def test_build_editorial_pack_has_review_and_layout(self, _mock_summary, _mock_ai):
        with TemporaryDirectory() as tmp_dir:
            hook_history_path = Path(tmp_dir) / "hook_history.json"
            pack = build_editorial_pack_for_item(self.item, hook_history_path=hook_history_path)

        self.assertIn("layout_plan", pack)
        self.assertIn("review", pack)
        self.assertTrue(pack["review"]["local_ok_after"])
        self.assertLessEqual(len(pack["layout_plan"]["hook_lines"]), HOOK_MAX_LINES)
        self.assertLessEqual(len(pack["layout_plan"]["tarja_lines"]), BODY_MAX_LINES)


if __name__ == "__main__":
    unittest.main()
