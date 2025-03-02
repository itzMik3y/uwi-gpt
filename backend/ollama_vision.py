import ollama

response = ollama.chat(
    model="minicpm-v:latest",
    messages=[
        {
            "role": "user",
            "content": "Extract the table from this image and return it as structured JSON.",
            "images": [r"C:\Users\Michael Webb\Pictures\Screenshots\Screenshot 2025-03-01 155516.png"]  # can also be a base64 string or bytes
        }
    ],
    stream=False  # optional, to get the full response at once
)

print(response["message"]["content"])
