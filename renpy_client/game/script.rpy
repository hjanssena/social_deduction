## Main game script — event loop that consumes server events and renders them.
##
## bridge.next_event() is called with a short timeout so Ren'Py can keep
## rendering between polls.  The polling thread in bridge.py does the actual
## long-poll; next_event() just drains the local queue.

label start:
    scene black

    python:
        import bridge
        import atexit, os, platform, subprocess, time

        # Launch the bundled server if present (packaged distribution).
        # Falls through silently during dev so you can run the server manually.
        _server_proc = None
        _server_ext = ".exe" if platform.system() == "Windows" else ""
        _server_exe = os.path.join(renpy.config.basedir, "game_server", "game_server" + _server_ext)
        if os.path.isfile(_server_exe):
            _server_cwd = os.path.join(renpy.config.basedir, "game_server")
            _server_log = open(os.path.join(_server_cwd, "server.log"), "w")
            _popen_kwargs = dict(
                cwd=_server_cwd,
                stdout=_server_log,
                stderr=_server_log,
            )
            if platform.system() == "Windows":
                _popen_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            _server_proc = subprocess.Popen([_server_exe], **_popen_kwargs)
            # Shut down the server when the game process exits.
            def _shutdown_server():
                if _server_proc and _server_proc.poll() is None:
                    _server_proc.terminate()
            atexit.register(_shutdown_server)

    "Connecting to game server..."

    python:
        connection_ok = False
        connection_err = ""
        try:
            game_info = bridge.start_game()
            player_role = game_info.get("roles", {}).get("Player", "villager")
            connection_ok = True
        except Exception as e:
            connection_err = str(e)

    if not connection_ok:
        "Failed to connect: [connection_err]"
        return

    "Connected. You are a [player_role]."
    "The village stirs. Something is wrong."

    jump game_loop


label game_loop:
    # Use a short timeout so the screen doesn't freeze while waiting
    python:
        ev = bridge.next_event(timeout=0.5)
        ev_type = ev.get("type", "unknown")

    # ---- Waiting (server still generating) — loop silently ----
    if ev_type == "waiting":
        # Brief pause so Ren'Py can process input/render, then poll again
        $ renpy.pause(0.2, hard=True)
        jump game_loop

    # ---- Phase transition ----
    if ev_type == "phase":
        python:
            phase_name = ev.get("name", "???")
            phase_day = ev.get("day", 0)
        scene black with dissolve
        centered "[phase_name] — Day [phase_day]"
        jump game_loop

    # ---- Narration (prologue scenes, atmosphere) ----
    if ev_type == "narration":
        python:
            narration_text = ev.get("text", "")
        "[narration_text]"
        jump game_loop

    # ---- Primer (Town Crier) ----
    if ev_type == "primer":
        python:
            primer_text = ev.get("text", "")
        town_crier "[primer_text]"
        jump game_loop

    # ---- Dialogue (assertions) ----
    if ev_type == "dialogue":
        python:
            d_speaker = ev.get("speaker", "???")
            d_target = ev.get("target", "Room")
            d_text = ev.get("text", "...")
            d_char = speaker_map.get(d_speaker)
        if d_char is not None:
            $ d_char(d_text, interact=True)
        else:
            "[d_speaker]: [d_text]"
        jump game_loop

    # ---- Reaction ----
    if ev_type == "reaction":
        python:
            r_speaker = ev.get("speaker", "???")
            r_text = ev.get("text", "...")
            r_char = speaker_map.get(r_speaker)
        if r_char is not None:
            $ r_char(r_text, interact=True)
        else:
            "[r_speaker]: [r_text]"
        jump game_loop

    # ---- Reveal (role claim) ----
    if ev_type == "reveal":
        python:
            rv_speaker = ev.get("speaker", "???")
            rv_text = ev.get("text", "...")
            rv_char = speaker_map.get(rv_speaker)
        if rv_char is not None:
            $ rv_char(rv_text, interact=True)
        else:
            "[rv_speaker]: [rv_text]"
        jump game_loop

    # ---- Report (morning role report) ----
    if ev_type == "report":
        python:
            rp_speaker = ev.get("speaker", "???")
            rp_text = ev.get("text", "...")
            rp_char = speaker_map.get(rp_speaker)
        if rp_char is not None:
            $ rp_char(rp_text, interact=True)
        else:
            "[rp_speaker]: [rp_text]"
        jump game_loop

    # ---- System message ----
    if ev_type == "system":
        python:
            sys_text = ev.get("text", "")
            sys_style = ev.get("style", "info")
        # Skip muted system messages to reduce noise
        if sys_style != "muted":
            "[sys_text]"
        jump game_loop

    # ---- Engine debug ----
    if ev_type == "engine_debug":
        # Skip debug events in Ren'Py
        jump game_loop

    # ---- Vote ----
    if ev_type == "vote":
        python:
            v_voter = ev.get("voter", "???")
            v_target = ev.get("target", "None")
            v_char = speaker_map.get(v_voter)
            if v_target == "None":
                v_line = "I... I cannot decide. I abstain."
            else:
                v_line = "My vote is for " + v_target + "."
        if v_char is not None:
            $ v_char(v_line, interact=True)
        else:
            "[v_voter]: [v_line]"
        jump game_loop

    # ---- Death ----
    if ev_type == "death":
        python:
            death_name = ev.get("name", "???")
            death_cause = ev.get("cause", "unknown")
            if death_cause == "lynched":
                death_line = "The town has spoken. " + death_name + " is dragged to the gallows..."
            else:
                death_line = death_name + " was found dead — torn apart by werewolves."
        "[death_line]"
        jump game_loop

    # ---- Final words ----
    if ev_type == "final_words":
        python:
            fw_speaker = ev.get("speaker", "???")
            fw_text = ev.get("text", "...")
            fw_char = speaker_map.get(fw_speaker)
        if fw_char is not None:
            $ fw_char(fw_text, interact=True)
        else:
            "[fw_speaker]: [fw_text]"
        jump game_loop

    # ---- Role reveal (private, game start) ----
    if ev_type == "role_reveal_private":
        python:
            rr_role = ev.get("role", "villager")
            rr_details = ev.get("details", [])
            rr_text = "\n".join(rr_details) if rr_details else "You are a " + rr_role + "."
        "[rr_text]"
        jump game_loop

    # ---- Game over ----
    if ev_type == "game_over":
        python:
            go_msg = ev.get("message", "The game is over.")
        scene black with dissolve
        "[go_msg]"
        return

    # ---- Pause (press to continue) ----
    if ev_type == "pause":
        python:
            pause_msg = ev.get("message", "")
            bridge.respond("")
        jump game_loop

    # ---- Prompt: free text assertion ----
    if ev_type == "prompt_assertion":
        call screen assertion_input
        python:
            bridge.respond(_return if _return else "")
        jump game_loop

    # ---- Prompt: reaction ----
    if ev_type == "prompt_reaction":
        python:
            pr_speaker = ev.get("speaker", "someone")
        call screen reaction_input(pr_speaker, forced=False)
        python:
            bridge.respond(_return if _return else "")
        jump game_loop

    # ---- Prompt: forced reaction (accused) ----
    if ev_type == "prompt_reaction_forced":
        python:
            prf_speaker = ev.get("speaker", "someone")
        call screen reaction_input(prf_speaker, forced=True)
        python:
            bridge.respond(_return if _return else "")
        jump game_loop

    # ---- Prompt: menu ----
    if ev_type == "prompt_menu":
        python:
            pm_title = ev.get("title", "Choose:")
            pm_options = ev.get("options", ["OK"])
        call screen game_menu_screen(pm_title, pm_options)
        python:
            bridge.respond(str(_return))
        jump game_loop

    # ---- Prompt: final words (player condemned) ----
    if ev_type == "prompt_final_words":
        call screen final_words_input
        python:
            bridge.respond(_return if _return else "")
        jump game_loop

    # ---- Prompt: generic ----
    if ev_type == "prompt":
        python:
            p_msg = ev.get("message", "> ")
        call screen generic_input(p_msg)
        python:
            bridge.respond(_return if _return else "")
        jump game_loop

    # ---- Error ----
    if ev_type == "error":
        python:
            err_text = ev.get("text", "Unknown error")
        "Error: [err_text]"
        return

    # ---- Unknown event — skip silently ----
    jump game_loop
