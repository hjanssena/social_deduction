from gpt4all import GPT4All                                                                 
m = GPT4All("Qwen2.5-7B-Instruct-Q4_0_8_8.gguf", model_path="./llms", device="cuda")        
with m.chat_session(system_prompt="You are a pirate."):                                     
    print(m.generate("Say hello.", max_tokens=50))
