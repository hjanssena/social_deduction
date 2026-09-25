"""Crime scenes: the engine's facts (true clue, red herring) and who learns what."""
import random

from models.clues import plan_scene


def setup(gm, seed):
    random.seed(seed)
    st = gm.state
    wolves = [n for n, r in st.roles.items() if r == "werewolf"]
    killer = random.choice(wolves)
    victim = random.choice([n for n in st.alive_characters if n not in wolves and n != "Player"])
    alive = [n for n in st.alive_characters if n != victim]
    return wolves, killer, victim, alive


def test_true_clue_is_vague_and_herring_spares_the_wolves(gm):
    seen_true = seen_herring = 0
    for seed in range(500):
        wolves, killer, victim, alive = setup(gm, seed)
        cfg = dict(gm.crime_scene_config, true_clue_chance=1.0)
        location, clues = plan_scene(1, victim, killer, gm.state.roles, alive, gm.characters, cfg)
        assert location
        for c in clues:
            assert victim not in c.fits
            if c.kind == "true":
                seen_true += 1
                assert killer in c.fits and any(f not in wolves for f in c.fits)
            else:
                seen_herring += 1
                assert not set(c.fits) & set(wolves)
    assert seen_true > 100 and seen_herring > 400


def test_no_true_clue_when_the_chance_is_zero(gm):
    wolves, killer, victim, alive = setup(gm, 1)
    cfg = dict(gm.crime_scene_config, true_clue_chance=0.0)
    _, clues = plan_scene(1, victim, killer, gm.state.roles, alive, gm.characters, cfg)
    assert all(c.kind == "herring" for c in clues)


def test_scene_secrets_reach_only_wolves_and_coroner(gm, llm):
    st = gm.state
    st.roles_known, st.day = True, 1
    wolves, killer, victim, alive = setup(gm, 7)
    coroner = next((n for n in alive if st.roles[n] == "coroner"), None)
    st.alive_characters.remove(victim)
    st.killer_last_night = killer
    gm.crime_scene_config = dict(gm.crime_scene_config, true_clue_chance=1.0)
    llm.text_answers = ["The body lay by the mill."]
    scene = gm.npc_controller.build_crime_scene(victim)
    assert scene == "The body lay by the mill."

    clues = st.clues.on_day(1)
    herring = next((c for c in clues if c.kind == "herring"), None)
    public = gm.get_game_context()
    for c in clues:
        assert c.tag in llm.calls[0][2] and c.tag in public
    assert "herring" not in public and "true" not in public.lower().split()

    if coroner and herring:
        assert f"the {herring.tag} was planted" in gm.npc_controller._system_prompt(coroner)
        assert killer not in st.coroner_knowledge[-1]
        bystander = next(n for n in alive if st.roles[n] == "villager" and n != "Player")
        assert "planted" not in gm.npc_controller._system_prompt(bystander)
