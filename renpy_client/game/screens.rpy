## Custom screens for player input.

## ---------- Assertion input (free text + skip) ----------
screen assertion_input():
    modal True

    default player_text = ""

    frame:
        xalign 0.5
        yalign 0.8
        xpadding 30
        ypadding 20
        xsize 900

        vbox:
            spacing 10

            text "Speak to the room, or stay silent." size 22

            input:
                value ScreenVariableInputValue("player_text")
                length 300
                pixel_width 840

            hbox:
                spacing 20
                xalign 0.5

                textbutton "Speak" action Return(player_text) sensitive len(player_text) > 0
                textbutton "Stay Silent" action Return("")


## ---------- Reaction input (free text + skip) ----------
screen reaction_input(speaker, forced=False):
    modal True

    default player_text = ""

    frame:
        xalign 0.5
        yalign 0.8
        xpadding 30
        ypadding 20
        xsize 900

        vbox:
            spacing 10

            if forced:
                text "You were accused by [speaker]! Defend yourself." size 22 color "#ff6666"
            else:
                text "React to [speaker], or stay silent." size 22

            input:
                value ScreenVariableInputValue("player_text")
                length 300
                pixel_width 840

            hbox:
                spacing 20
                xalign 0.5

                textbutton "React" action Return(player_text) sensitive len(player_text) > 0
                textbutton "Stay Silent" action Return("")


## ---------- Menu screen (voting, night target, GA protection) ----------
screen game_menu_screen(title, options):
    modal True

    frame:
        xalign 0.5
        yalign 0.5
        xpadding 40
        ypadding 30

        vbox:
            spacing 15

            text title size 26

            for idx, opt in enumerate(options):
                textbutton opt action Return(idx)


## ---------- Final words (condemned player) ----------
screen final_words_input():
    modal True

    default player_text = ""

    frame:
        xalign 0.5
        yalign 0.8
        xpadding 30
        ypadding 20
        xsize 900

        vbox:
            spacing 10

            text "Speak your final words..." size 22 color "#ffcc00"

            input:
                value ScreenVariableInputValue("player_text")
                length 300
                pixel_width 840

            hbox:
                spacing 20
                xalign 0.5

                textbutton "Speak" action Return(player_text) sensitive len(player_text) > 0
                textbutton "Say Nothing" action Return("")


## ---------- Generic text input ----------
screen generic_input(prompt_text):
    modal True

    default player_text = ""

    frame:
        xalign 0.5
        yalign 0.8
        xpadding 30
        ypadding 20
        xsize 900

        vbox:
            spacing 10

            text prompt_text size 22

            input:
                value ScreenVariableInputValue("player_text")
                length 300
                pixel_width 840

            hbox:
                spacing 20
                xalign 0.5

                textbutton "Submit" action Return(player_text) sensitive len(player_text) > 0
                textbutton "Skip" action Return("")
