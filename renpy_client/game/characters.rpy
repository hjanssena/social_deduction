## Character definitions for the social deduction visual novel.
## Each NPC gets a unique text color. The player character uses white.

## narrator is Ren'Py's built-in — no need to redefine it.

define player = Character("You", color="#ffffff")
define town_crier = Character("Town Crier", color="#d4a017")

define elias = Character("Elias", color="#c0392b")       # Blacksmith — red
define silas = Character("Silas", color="#2980b9")        # Scholar — blue
define victor = Character("Victor", color="#8e44ad")      # Mayor — purple
define elara = Character("Elara", color="#e67e22")        # Baker — orange
define garrick = Character("Garrick", color="#27ae60")    # Tavern Keeper — green
define bram = Character("Bram", color="#7f8c8d")          # Village Elder — grey
define maeve = Character("Maeve", color="#1abc9c")        # Gravedigger — teal

# Lookup dict so bridge.py can resolve speaker names to Character objects.
define speaker_map = {
    "Elias": elias,
    "Silas": silas,
    "Victor": victor,
    "Elara": elara,
    "Garrick": garrick,
    "Bram": bram,
    "Maeve": maeve,
    "Player": player,
    "Town Crier": town_crier,
}
