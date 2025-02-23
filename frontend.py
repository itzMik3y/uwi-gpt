import flet as ft
import requests
import json
import threading
import time
from math import pi

def main(page: ft.Page):
    page.title = "UWI GPT"
    page.vertical_alignment = ft.MainAxisAlignment.START
    page.padding = 20
    qa_history = ft.Column(scroll="adaptive", expand=True)

    # Animated loading dots
    loading_dots = [
        ft.Container(
            content=ft.Text(".", size=30),
            opacity=0,
            rotate=ft.transform.Rotate(0),
            scale=ft.transform.Scale(1),
            offset=ft.transform.Offset(0, 0),
            animate_opacity=500,
            animate_rotation=ft.animation.Animation(500, ft.AnimationCurve.EASE_IN_OUT),
            animate_scale=ft.animation.Animation(500, ft.AnimationCurve.EASE_IN_OUT),
            animate_offset=ft.animation.Animation(500, ft.AnimationCurve.EASE_IN_OUT),
        )
        for _ in range(3)
    ]
    
    error_message = ft.Text("", color=ft.Colors.RED, visible=False)

    txt_query = ft.TextField(label="Enter your query...", expand=True)
    btn_submit = ft.ElevatedButton("Submit")

    input_row = ft.Row([txt_query, btn_submit])

    loading = False  # Flag to track loading state

    def animate_loading():
        """Continuous loading animation until response arrives."""
        nonlocal loading
        loading = True
        while loading:
            for i, dot in enumerate(loading_dots):
                dot.opacity = 1 if dot.opacity == 0 else 0.3
                dot.rotate.angle += pi / 4
                dot.scale = 1.2 if dot.scale == 1 else 1
                dot.offset = ft.transform.Offset(-0.2, 0) if dot.offset.x == 0 else ft.transform.Offset(0.2, 0)
                dot.update()
                time.sleep(0.3)  # Delay between each dot animation
        # Reset dots after animation stops
        for dot in loading_dots:
            dot.opacity = 0
            dot.update()

    def submit_click(e):
        query = txt_query.value.strip()
        if not query:
            return

        # Disable UI elements
        error_message.visible = False
        txt_query.disabled = True
        btn_submit.disabled = True
        for dot in loading_dots:
            dot.opacity = 0.3  # Make dots visible initially
        page.update()

        # Start animation thread
        threading.Thread(target=animate_loading, daemon=True).start()

        def fetch_answer():
            """Fetch response in a separate thread from the FastAPI backend."""
            nonlocal loading
            try:
                # Send request to FastAPI endpoint
                response = requests.post(
                    'http://127.0.0.1:8000/query',  # Adjust with actual FastAPI endpoint
                    json={'query': query},
                    timeout=120
                )
                response.raise_for_status()
                data = response.json()

                # Handle the response data
                if 'answer' in data:
                    add_response(query, data['answer'])
                elif 'error' in data:
                    show_error(data['error'])
                else:
                    show_error("Unexpected response format.")

            except requests.exceptions.RequestException as ex:
                show_error(f"Network Error: {ex}")
            except json.JSONDecodeError as ex:
                show_error(f"Invalid JSON: {ex}")
            except Exception as ex:
                show_error(f"An error occurred: {ex}")
            finally:
                loading = False  # Stop animation
                reset_ui()

        threading.Thread(target=fetch_answer, daemon=True).start()

    def add_response(question, answer):
        """Updates UI with QA response."""
        qa_history.controls.append(ft.Markdown(f"**Student:** {question}"))
        qa_history.controls.append(ft.Markdown(f"**Answer:** {answer}"))
        page.update()

    def show_error(message):
        """Displays error message."""
        error_message.value = message
        error_message.visible = True
        page.update()

    def reset_ui():
        """Resets UI after response."""
        txt_query.disabled = False
        btn_submit.disabled = False
        txt_query.value = ""
        page.update()

    # Event listeners
    btn_submit.on_click = submit_click
    txt_query.on_submit = submit_click

    page.add(qa_history, ft.Row(loading_dots, alignment=ft.MainAxisAlignment.CENTER), error_message, input_row)

# Run the app
ft.app(target=main, assets_dir="assets")
