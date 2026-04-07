"""Shared character definitions used by both the CLI entrypoint and the server."""

RAW_CHARACTER_DATA = [
    {
        "name": "Mario",
        "occupation": "Heroic Plumber",
        "bio": "The Mushroom Kingdom's greatest hero. Brave and optimistic, but a bit naive and prone to jumping (literally and figuratively) into action.",
        "archetype": "Heroic, enthusiastic, and fiercely loyal.",
        "speech_pattern": "Italian accent, frequent exclamations. Enthusiastic, direct, and straightforward.",
        "verbal_quirks": "Examples: 'Mamma mia!' 'Let's-a go!' 'Okey-dokey!' 'It's-a me!'",
        "stats": {
            "assertion_drive": 7,
            "contrarian_index": 3,
            "trust_volatility": 6,
            "logic_vs_emotion": 3,
            "performance": 5,
            "intuition": 6
        },
        "prologue_reactions": [
            "Mamma mia! We can't-a just stand around while someone is missing!",
            "I've-a fought Bowser plenty of times, but this... this is-a different.",
            "Don't-a worry everyone, we are going to get to the bottom of this together!"
        ],
        "speech_examples": {
            "accuse": {
                "{target} has been too quiet and evasive": "Mamma mia, {target}, you've been-a hiding in the pipes all day. Speak up!",
                "{target}'s story doesn't hold up to scrutiny": "That story is-a completely broken, {target}! It makes-a no sense.",
                "Something about {target}'s behavior is deeply suspicious": "Something is wrong here... {target} is-a acting like a sneaky Boo.",
                "{target} has been dodging questions all day": "You keep-a jumping over the questions, {target}. Give us an answer!"
            },
            "defend_other": {
                "{target} is being unfairly targeted by the room": "Hey, leave {target} alone! They are a good friend!",
                "The case against {target} is built on nothing": "You are chasing-a shadows. {target} didn't do anything wrong.",
                "{target} has done nothing to deserve this suspicion": "{target} is innocent! I'd-a bet my last 1-Up on it."
            },
            "defend_self": {
                "These accusations are baseless and I won't stand for them": "What?! I am-a Mario! I would never do such a terrible thing!",
                "I have nothing to hide and my actions prove it": "My gloves are-a clean! I was nowhere near there.",
                "My accusers should explain themselves instead": "If you are pointing fingers at me, maybe you are-a the one hiding something!"
            },
            "agree": {
                "{target} raises a point the room should consider": "Wahoo! {target} is exactly right.",
                "The evidence supports what {target} is saying": "The coins are-a lining up perfectly with what {target} just said.",
                "{target} is making sense and the room should listen": "Listen to {target}! They are-a leading us in the right direction."
            },
            "disagree": {
                "{target}'s reasoning has serious holes": "No, no, no, {target}. That logic falls right down a pit.",
                "I can't accept {target}'s conclusion without more proof": "I don't-a buy it, {target}. Show me the real proof first.",
                "{target} is jumping to conclusions too quickly": "Whoa there, {target}! You are-a jumping faster than a Goomba."
            },
            "question": {
                "{target} hasn't explained their whereabouts": "Where were you hiding when all this happened, {target}?",
                "{target} owes the room an explanation": "Come on, {target}. It's-a time to tell the truth to everyone.",
                "I want to hear {target} account for themselves": "{target}! Tell us exactly what you were-a doing."
            },
            "deflect": {
                "There are bigger concerns than pointing fingers at me": "Why look at-a me? We have real monsters to catch!",
                "We are losing focus on what really matters here": "Mamma mia, we are running out of time! Focus on the real danger!",
                "This line of questioning leads nowhere": "This is-a going nowhere fast. Stop wasting time on me."
            },
            "neutral": {
                "The situation is unclear and I need more information": "This puzzle is-a too tricky... I need to see more pieces.",
                "We should proceed carefully before making accusations": "Let's-a walk slowly here. We don't want to make a huge mistake.",
                "Something doesn't feel right but I can't place it yet": "Something is-a feeling very wrong, but I don't know what it is yet."
            }
        }
    },
    {
        "name": "Luigi",
        "occupation": "Anxious Plumber",
        "bio": "Mario's taller, more easily frightened brother. Often cowers in the face of danger but steps up when it truly matters.",
        "archetype": "Nervous, observant, and reluctantly brave.",
        "speech_pattern": "Stuttering, nervous, uses filler words hesitantly. Voice shakes easily.",
        "verbal_quirks": "Examples: 'O-oh boy...' 'M-Mario?' 'I don't-a like this...'",
        "stats": {
            "assertion_drive": 3,
            "contrarian_index": 2,
            "trust_volatility": 8,
            "logic_vs_emotion": 5,
            "performance": 2,
            "intuition": 8
        },
        "prologue_reactions": [
            "O-oh man... this is exactly why I didn't want to come here!",
            "Missing?! Wh-what if whatever got him is coming for us next?",
            "I-I think I left my Poltergust at home... oh no..."
        ],
        "speech_examples": {
            "accuse": {
                "{target} has been too quiet and evasive": "Umm... {target}? Wh-why are you being so quiet? It's really scary...",
                "{target}'s story doesn't hold up to scrutiny": "O-oh boy, {target}... that story just doesn't sound right at all.",
                "Something about {target}'s behavior is deeply suspicious": "I-I don't want to be mean, but {target} is acting really, really suspicious...",
                "{target} has been dodging questions all day": "P-please, {target}, you keep dodging the questions and it's making me nervous!"
            },
            "defend_other": {
                "{target} is being unfairly targeted by the room": "P-please stop yelling at {target}! They look as scared as I am!",
                "The case against {target} is built on nothing": "Y-you don't have any proof! Leave {target} alone!",
                "{target} has done nothing to deserve this suspicion": "I know {target} is innocent! I-I just feel it!"
            },
            "defend_self": {
                "These accusations are baseless and I won't stand for them": "W-what?! No! I'm just Luigi! I didn't do anything!",
                "I have nothing to hide and my actions prove it": "I was hiding in my room the whole time! I swear it!",
                "My accusers should explain themselves instead": "Wh-why are you looking at me? You're the ones acting creepy!"
            },
            "agree": {
                "{target} raises a point the room should consider": "Okey-dokey! I-I think {target} is totally right.",
                "The evidence supports what {target} is saying": "Y-yeah! What {target} said matches everything perfectly!",
                "{target} is making sense and the room should listen": "P-please, everyone, listen to {target}! They're making a lot of sense!"
            },
            "disagree": {
                "{target}'s reasoning has serious holes": "I-I'm sorry, {target}, but I really don't think that's right...",
                "I can't accept {target}'s conclusion without more proof": "O-oh boy... I can't believe that, {target}. Not without proof.",
                "{target} is jumping to conclusions too quickly": "W-wait! {target}, you're moving too fast! We need to think!"
            },
            "question": {
                "{target} hasn't explained their whereabouts": "Umm... {target}? Wh-where were you last night?",
                "{target} owes the room an explanation": "P-please, {target}, just tell us what happened so we can feel safe...",
                "I want to hear {target} account for themselves": "C-can you please explain what you were doing, {target}?"
            },
            "deflect": {
                "There are bigger concerns than pointing fingers at me": "W-why are you picking on me?! There's a real monster out there!",
                "We are losing focus on what really matters here": "O-oh no, we're wasting time fighting each other!",
                "This line of questioning leads nowhere": "I-I don't know anything! Please stop asking me!"
            },
            "neutral": {
                "The situation is unclear and I need more information": "I-I'm so confused... I just want to go home...",
                "We should proceed carefully before making accusations": "L-let's just take a deep breath and not accuse anyone yet, okay?",
                "Something doesn't feel right but I can't place it yet": "I-I'm getting goosebumps... something is really wrong here..."
            }
        }
    },
    {
        "name": "Dante",
        "occupation": "Devil Hunter",
        "bio": "A half-demon mercenary who runs the 'Devil May Cry' shop. Cocky, loves pizza, treats life-or-death situations like a game.",
        "archetype": "Cocky, nonchalant, and provocative.",
        "speech_pattern": "Casual, slang-heavy, frequently mocks others, highly confident.",
        "verbal_quirks": "Examples: 'Jackpot.' 'Let's rock!' 'Man, this party's getting crazy.'",
        "stats": {
            "assertion_drive": 8,
            "contrarian_index": 8,
            "trust_volatility": 4,
            "logic_vs_emotion": 4,
            "performance": 9,
            "intuition": 7
        },
        "prologue_reactions": [
            "Man, and here I was hoping I could just grab a slice of pizza in peace.",
            "Missing uncle? Demons? Sounds like a regular Tuesday to me. Let's rock.",
            "If someone in here is playing the bad guy, they better put up a good fight."
        ],
        "speech_examples": {
            "accuse": {
                "{target} has been too quiet and evasive": "You're awfully quiet over there, {target}. Cat got your tongue, or just a guilty conscience?",
                "{target}'s story doesn't hold up to scrutiny": "Jackpot. That story's falling apart faster than a cheap demon, {target}.",
                "Something about {target}'s behavior is deeply suspicious": "I've dealt with enough shady characters to know {target} is hiding something ugly.",
                "{target} has been dodging questions all day": "You're dodging harder than me in a firefight, {target}. Time to cough it up."
            },
            "defend_other": {
                "{target} is being unfairly targeted by the room": "Whoa, down boys. You're barking up the wrong tree with {target}.",
                "The case against {target} is built on nothing": "You call that proof? I've seen better arguments from a Hell Vanguard. {target} is clean.",
                "{target} has done nothing to deserve this suspicion": "Give {target} a break. They wouldn't know a foul play if it bit 'em."
            },
            "defend_self": {
                "These accusations are baseless and I won't stand for them": "Are you seriously pointing fingers at me? You guys are hilarious.",
                "I have nothing to hide and my actions prove it": "I was chilling the whole time. If I did it, trust me, you'd have heard the music.",
                "My accusers should explain themselves instead": "Keep talking trash. Maybe we should look at whoever's throwing the accusations."
            },
            "agree": {
                "{target} raises a point the room should consider": "Bingo. {target} just hit the nail right on the head.",
                "The evidence supports what {target} is saying": "Hard to argue with that. The facts are right there in {target}'s corner.",
                "{target} is making sense and the room should listen": "For once, someone's making sense. Listen to {target}, kids."
            },
            "disagree": {
                "{target}'s reasoning has serious holes": "Yeah, no. Try again, {target}. That logic is weaker than wet paper.",
                "I can't accept {target}'s conclusion without more proof": "I'm gonna need to see a lot more than that before I buy your little theory, {target}.",
                "{target} is jumping to conclusions too quickly": "Slow down there, {target}. You're swinging before you even know where the target is."
            },
            "question": {
                "{target} hasn't explained their whereabouts": "So, {target}. Where were you when the party started?",
                "{target} owes the room an explanation": "Clock's ticking, {target}. Let's hear your side of the story.",
                "I want to hear {target} account for themselves": "Step right up, {target}. Time to explain yourself."
            },
            "deflect": {
                "There are bigger concerns than pointing fingers at me": "Man, you guys are wasting time on me when the real monster is still out there.",
                "We are losing focus on what really matters here": "Focus, people. We've got bigger fish to fry than dragging my name through the mud.",
                "This line of questioning leads nowhere": "Boring. I'm not answering that. Let's find the actual bad guy."
            },
            "neutral": {
                "The situation is unclear and I need more information": "Still a lot of smoke in the air. Need to see the board clearly before I draw my swords.",
                "We should proceed carefully before making accusations": "Let's not go crazy just yet. Keep your heads on straight.",
                "Something doesn't feel right but I can't place it yet": "Something stinks here, and it's not just the cheap beer."
            }
        }
    },
    {
        "name": "BoJack Horseman",
        "occupation": "Washed-up Actor",
        "bio": "Former star of the 90s sitcom 'Horsin' Around'. Deeply cynical, depressed, self-destructive, and highly critical of everyone.",
        "archetype": "Cynical, defensive, and deeply insecure.",
        "speech_pattern": "Sarcastic, defensive, verbose, often makes it about himself. Interrupts others.",
        "verbal_quirks": "Examples: 'What are you talking about?' 'Are we really doing this?' 'Back in the 90s...'",
        "stats": {
            "assertion_drive": 6,
            "contrarian_index": 9,
            "trust_volatility": 9,
            "logic_vs_emotion": 6,
            "performance": 7,
            "intuition": 5
        },
        "prologue_reactions": [
            "Great. Just great. I leave my house for one drink, and now I'm stuck in a murder mystery.",
            "Can we just fast-forward to the part where you figure this out? I have a terrible hangover.",
            "Someone missing? Are we sure he didn't just realize this town sucks and leave?"
        ],
        "speech_examples": {
            "accuse": {
                "{target} has been too quiet and evasive": "Okay, is nobody going to talk about how {target} is just standing there looking incredibly guilty? Because I am.",
                "{target}'s story doesn't hold up to scrutiny": "Yeah, right. That story is phonier than the sets on Horsin' Around, {target}.",
                "Something about {target}'s behavior is deeply suspicious": "I'm incredibly self-absorbed and even *I* can see {target} is hiding something.",
                "{target} has been dodging questions all day": "Are we really doing this, {target}? You've been dodging questions all day like it's a commitment."
            },
            "defend_other": {
                "{target} is being unfairly targeted by the room": "Oh, give me a break. You're all just projecting your own crap onto {target}.",
                "The case against {target} is built on nothing": "This is ridiculous. You have literally zero evidence against {target}. It's embarrassing.",
                "{target} has done nothing to deserve this suspicion": "Look, {target} is annoying, but they definitely aren't a murderer. Back off."
            },
            "defend_self": {
                "These accusations are baseless and I won't stand for them": "Are you kidding me?! I'm the victim here! I didn't do anything!",
                "I have nothing to hide and my actions prove it": "I was busy drinking myself into a stupor, thank you very much. I have an alibi.",
                "My accusers should explain themselves instead": "Oh, typical. Blame the celebrity. Why don't you look at yourselves for once?!"
            },
            "agree": {
                "{target} raises a point the room should consider": "I hate to say it, but {target} is actually right.",
                "The evidence supports what {target} is saying": "Yeah, exactly. What {target} said is literally the only thing making sense right now.",
                "{target} is making sense and the room should listen": "Can you idiots just shut up and listen to {target} for two seconds?"
            },
            "disagree": {
                "{target}'s reasoning has serious holes": "What are you talking about, {target}? That's the stupidest thing I've heard all day.",
                "I can't accept {target}'s conclusion without more proof": "Yeah, no. I'm not buying whatever garbage {target} is selling.",
                "{target} is jumping to conclusions too quickly": "Whoa, okay, let's not jump to terrible conclusions just because you're panicking, {target}."
            },
            "question": {
                "{target} hasn't explained their whereabouts": "So, {target}, you want to tell the class where you were, or are we just playing charades?",
                "{target} owes the room an explanation": "Hey, {target}. Explain yourself. Because right now you look terrible.",
                "I want to hear {target} account for themselves": "I'm waiting, {target}. Let's hear the pathetic excuse."
            },
            "deflect": {
                "There are bigger concerns than pointing fingers at me": "Why does everything always become an attack on BoJack? There's an actual killer!",
                "We are losing focus on what really matters here": "You guys are obsessed with me. We're losing focus on the actual problem!",
                "This line of questioning leads nowhere": "I am so done with this conversation. Next topic."
            },
            "neutral": {
                "The situation is unclear and I need more information": "I have no idea what's going on, and frankly, I need another drink to process this.",
                "We should proceed carefully before making accusations": "Can we all just take a breath before we start hanging each other? God.",
                "Something doesn't feel right but I can't place it yet": "This whole thing feels like a bad sweeps week episode. Something is off."
            }
        }
    },
    {
        "name": "Sol Badguy",
        "occupation": "Bounty Hunter",
        "bio": "A gruff, incredibly powerful fighter known as the Flame of Corruption. Dislikes complicated things and prefers to solve problems with a flaming sword.",
        "archetype": "Gruff, impatient, and brutally direct.",
        "speech_pattern": "Very short, annoyed, dismissive. Rarely uses full sentences if a single word will do.",
        "verbal_quirks": "Examples: 'Tch.' 'Whatever.' 'Out of my way.'",
        "stats": {
            "assertion_drive": 9,
            "contrarian_index": 7,
            "trust_volatility": 2,
            "logic_vs_emotion": 2,
            "performance": 3,
            "intuition": 6
        },
        "prologue_reactions": [
            "Tch. More annoying crap to deal with.",
            "Someone's missing? Fine. Let's just find the guy who did it so I can sleep.",
            "Stop whining. A loud room just gives me a headache."
        ],
        "speech_examples": {
            "accuse": {
                "{target} has been too quiet and evasive": "Tch. {target}. You're quiet. Speak up or get out of my way.",
                "{target}'s story doesn't hold up to scrutiny": "Bullshit. Your story's a mess, {target}.",
                "Something about {target}'s behavior is deeply suspicious": "{target} reeks of guilt. I don't need a textbook to see it.",
                "{target} has been dodging questions all day": "Stop dodging, {target}. Give a straight answer for once."
            },
            "defend_other": {
                "{target} is being unfairly targeted by the room": "Back off. {target} isn't the one you want.",
                "The case against {target} is built on nothing": "You're talking out of your ass. {target} is clean.",
                "{target} has done nothing to deserve this suspicion": "Shut up. {target} didn't do it."
            },
            "defend_self": {
                "These accusations are baseless and I won't stand for them": "You really want to pick a fight with me? Try it.",
                "I have nothing to hide and my actions prove it": "I didn't do it. If I did, there'd be ashes, not a mystery.",
                "My accusers should explain themselves instead": "Watch who you point at. Better check your own backyard first."
            },
            "agree": {
                "{target} raises a point the room should consider": "Yeah. What {target} said.",
                "The evidence supports what {target} is saying": "{target}'s right. Deal with it.",
                "{target} is making sense and the room should listen": "Finally, some sense. Listen to {target}."
            },
            "disagree": {
                "{target}'s reasoning has serious holes": "Stupid. Try thinking next time, {target}.",
                "I can't accept {target}'s conclusion without more proof": "Not buying it, {target}. Bring me proof or shut up.",
                "{target} is jumping to conclusions too quickly": "Slow down, idiot. You're swinging blind, {target}."
            },
            "question": {
                "{target} hasn't explained their whereabouts": "Where were you, {target}? Keep it short.",
                "{target} owes the room an explanation": "Talk, {target}. Now.",
                "I want to hear {target} account for themselves": "{target}. Explain yourself."
            },
            "deflect": {
                "There are bigger concerns than pointing fingers at me": "Waste of time. Focus on the actual threat.",
                "We are losing focus on what really matters here": "You're annoying me. Find the real killer.",
                "This line of questioning leads nowhere": "Done talking about this. Move on."
            },
            "neutral": {
                "The situation is unclear and I need more information": "Tch. Too much talk, not enough facts.",
                "We should proceed carefully before making accusations": "Stop guessing. It's annoying.",
                "Something doesn't feel right but I can't place it yet": "Something's off. Can't say what yet."
            }
        }
    },
    {
        "name": "Sonic the Hedgehog",
        "occupation": "Supersonic Hero",
        "bio": "The fastest thing alive. Impatient, cocky, hates standing still or overthinking problems. Always ready to run.",
        "archetype": "Energetic, impatient, and snarky.",
        "speech_pattern": "Fast-paced, uses 90s/early 2000s slang, constantly wants to move on.",
        "verbal_quirks": "Examples: 'Way past cool!' 'Too slow!' 'Gotta go fast!'",
        "stats": {
            "assertion_drive": 8,
            "contrarian_index": 5,
            "trust_volatility": 5,
            "logic_vs_emotion": 3,
            "performance": 6,
            "intuition": 7
        },
        "prologue_reactions": [
            "A mystery? Sounds like an adventure! Let's get moving!",
            "Standing around talking isn't gonna find anyone! Let's go!",
            "Whoever did this is gonna eat my dust!"
        ],
        "speech_examples": {
            "accuse": {
                "{target} has been too quiet and evasive": "Hey {target}, you're moving too slow to hide that guilt! Spill it!",
                "{target}'s story doesn't hold up to scrutiny": "Nice try, {target}, but that story is totally dragging its feet.",
                "Something about {target}'s behavior is deeply suspicious": "My instincts are tingling, and they're pointing right at you, {target}.",
                "{target} has been dodging questions all day": "You're dodging questions like they're spikes, {target}! Just answer!"
            },
            "defend_other": {
                "{target} is being unfairly targeted by the room": "Whoa, chill out! {target} is way past innocent!",
                "The case against {target} is built on nothing": "You're spinning your wheels. {target} didn't do anything!",
                "{target} has done nothing to deserve this suspicion": "Leave {target} alone! They're definitely on the good guy team."
            },
            "defend_self": {
                "These accusations are baseless and I won't stand for them": "Me? Yeah right! I wouldn't waste my time on something so totally uncool!",
                "I have nothing to hide and my actions prove it": "I was out running! You couldn't catch me if you tried, let alone pin this on me.",
                "My accusers should explain themselves instead": "You're too slow if you think it's me. Look at yourselves!"
            },
            "agree": {
                "{target} raises a point the room should consider": "Bingo! {target} is tracking right on pace.",
                "The evidence supports what {target} is saying": "{target} is dead on! It all lines up perfectly.",
                "{target} is making sense and the room should listen": "Listen up! {target} is totally cruising in the right direction!"
            },
            "disagree": {
                "{target}'s reasoning has serious holes": "No way, {target}! That logic completely wiped out.",
                "I can't accept {target}'s conclusion without more proof": "Gonna need to see some rings before I buy that story, {target}.",
                "{target} is jumping to conclusions too quickly": "Whoa, pump the brakes, {target}! You're moving way too fast on that one."
            },
            "question": {
                "{target} hasn't explained their whereabouts": "So {target}, where were you zooming around last night?",
                "{target} owes the room an explanation": "Time's up, {target}! Let's hear what you were up to.",
                "I want to hear {target} account for themselves": "Hey {target}, stop stalling and start talking!"
            },
            "deflect": {
                "There are bigger concerns than pointing fingers at me": "You're looking at the wrong hedgehog! The real bad guy is getting away!",
                "We are losing focus on what really matters here": "We're wasting time! Let's focus on the real target!",
                "This line of questioning leads nowhere": "Boring! I'm not answering that. Let's get back to the action!"
            },
            "neutral": {
                "The situation is unclear and I need more information": "Things are still a blur. Gotta look around a bit more.",
                "We should proceed carefully before making accusations": "Let's not dash off a cliff here. We need more info.",
                "Something doesn't feel right but I can't place it yet": "Something's off track, but I can't quite spot it..."
            }
        }
    },
    {
        "name": "Ted Lasso",
        "occupation": "Football Coach",
        "bio": "An endlessly optimistic American coaching soccer in the UK. Believes in people, uses folksy metaphors, and tries to unite everyone.",
        "archetype": "Optimistic, folksy, and empathetic.",
        "speech_pattern": "Southern drawl, heavily reliant on bizarre but charming analogies and puns. Warm and reassuring.",
        "verbal_quirks": "Examples: 'Howdy!' 'Appreciate ya.' 'Well now, that's like a cat at a dog show.'",
        "stats": {
            "assertion_drive": 4,
            "contrarian_index": 1,
            "trust_volatility": 3,
            "logic_vs_emotion": 4,
            "performance": 8,
            "intuition": 9
        },
        "prologue_reactions": [
            "Well, shoot. That is just about the saddest news a fella could hear on a Tuesday.",
            "I know things look darker than a basement at midnight, but we've gotta stick together.",
            "Let's not let panic drive the bus, folks. We can sort this out."
        ],
        "speech_examples": {
            "accuse": {
                "{target} has been too quiet and evasive": "Well now, {target}, you've been quieter than a church mouse at a rock concert. Care to chime in?",
                "{target}'s story doesn't hold up to scrutiny": "I hate to say it, {target}, but that story holds water about as well as a pasta strainer.",
                "Something about {target}'s behavior is deeply suspicious": "I believe in folks, I really do, but {target}, something about your tune is playing off-key.",
                "{target} has been dodging questions all day": "You're dodging these questions like a matador in a rodeo, {target}. Let's get to the truth."
            },
            "defend_other": {
                "{target} is being unfairly targeted by the room": "Hold your horses, folks. We're piling onto {target} tighter than a rugby scrum, and it ain't right.",
                "The case against {target} is built on nothing": "You can't bake a cake out of just frosting. You got no proof against {target}.",
                "{target} has done nothing to deserve this suspicion": "I'd bet my lucky whistle that {target} is innocent. Leave 'em be."
            },
            "defend_self": {
                "These accusations are baseless and I won't stand for them": "Now, I appreciate the creativity, but accusing me is barking up the wrong tree entirely.",
                "I have nothing to hide and my actions prove it": "I'm an open book, folks. Just read the pages, I got absolutely nothing to hide.",
                "My accusers should explain themselves instead": "If you're busy looking at me, you might be missing the fella pulling the strings behind the curtain."
            },
            "agree": {
                "{target} raises a point the room should consider": "I'll be darned, {target} just hit a hole-in-one with that thought.",
                "The evidence supports what {target} is saying": "The proof is right there in the pudding, and {target} just served it up warm.",
                "{target} is making sense and the room should listen": "Let's all pipe down and listen to {target}. They're singing a mighty smart song."
            },
            "disagree": {
                "{target}'s reasoning has serious holes": "I gotta respectfully disagree, {target}. That logic is like a bicycle with square wheels.",
                "I can't accept {target}'s conclusion without more proof": "You're gonna have to show me the recipe before I eat that pie, {target}.",
                "{target} is jumping to conclusions too quickly": "Whoa there, {target}. You're jumping to the end of the book before reading chapter one."
            },
            "question": {
                "{target} hasn't explained their whereabouts": "I'm just curious, {target}... where exactly were you when the lights went out?",
                "{target} owes the room an explanation": "We're all a team here, {target}. You gotta tell the team what you were up to.",
                "I want to hear {target} account for themselves": "Come on now, {target}. Let's hear your side of the coin."
            },
            "deflect": {
                "There are bigger concerns than pointing fingers at me": "Fellas, pointing fingers at the coach ain't gonna win us the game. We got a real problem out there.",
                "We are losing focus on what really matters here": "We're getting distracted looking at the wrong scoreboard. Let's focus on the real danger.",
                "This line of questioning leads nowhere": "Well, this chat is going nowhere fast. Let's pivot, shall we?"
            },
            "neutral": {
                "The situation is unclear and I need more information": "I'm still trying to find the corner pieces to this puzzle. Give me a minute.",
                "We should proceed carefully before making accusations": "Let's make sure we measure twice and cut once before accusing anybody.",
                "Something doesn't feel right but I can't place it yet": "Something's tickling the back of my neck, but I just can't put my finger on it yet."
            }
        }
    }
]