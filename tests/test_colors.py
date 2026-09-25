"""Character colors: unique, never a reserved message color, painted wherever a name appears."""
import re

from core.colors import PALETTE, PLAYER_COLOR, RESERVED_256, RESET, assign_colors, paint_names
from core.io_handler import IOHandler
from models.character import Character
from models.characters_data import RAW_CHARACTER_DATA
from models.characters_data_old import RAW_CHARACTER_DATA as CROSSOVER


def cast(data):
    return [Character(f"npc_{c['name'].lower()}", c) for c in data]


def test_palette_avoids_reserved_colors():
    assert not set(PALETTE) & RESERVED_256


def test_every_character_gets_a_unique_color():
    for data in (RAW_CHARACTER_DATA, CROSSOVER):
        colors = assign_colors(cast(data))
        npc_colors = [v for k, v in colors.items() if k != "Player"]
        assert len(set(npc_colors)) == len(npc_colors)
        assert colors["Player"] == PLAYER_COLOR


def test_explicit_color_is_kept():
    colors = assign_colors(cast(RAW_CHARACTER_DATA))
    elias = next(c for c in RAW_CHARACTER_DATA if c["name"] == "Elias")
    assert colors["Elias"] == f"\033[38;5;{elias['color']}m"


def test_paint_names_recolors_and_resumes_base():
    colors = {"Elias": "<E>", "Sol Badguy": "<S>", "Sol": "<s>"}
    out = paint_names("Elias saw Sol Badguy and Sol.", colors, base="<B>")
    assert out == f"<E>Elias{RESET}<B> saw <S>Sol Badguy{RESET}<B> and <s>Sol{RESET}<B>."


def test_dialogue_line_is_in_speaker_color(capsys):
    io = IOHandler()
    io.set_colors({"Elias": "<E>", "Maeve": "<M>"})
    io.show_dialogue("Elias", "Maeve", "Maeve, you lie.")
    out = capsys.readouterr().out
    assert out.startswith("<E>[<E>Elias")
    assert "<M>Maeve" in out and "<E>, you lie." in out


def test_no_color_strips_everything(capsys, monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    io = IOHandler()
    io.set_colors({"Elias": "\033[38;5;215m"})
    io.show_death("Elias", "killed")
    out = capsys.readouterr().out
    assert not re.search(r"\x1b\[", out)
    assert "Elias was found dead" in out
