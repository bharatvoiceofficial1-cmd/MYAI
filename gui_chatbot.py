import json
import queue
import threading
import tkinter as tk
from tkinter import messagebox
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

MODEL = "qwen2.5:0.5b"
OLLAMA_URL = "http://localhost:11434/api/chat"

BG = "#171717"
PANEL = "#212121"
USER_BUBBLE = "#303030"
TEXT = "#f5f5f5"
MUTED = "#a8a8a8"


class LocalChatbot:
    def __init__(self, root):
        self.root = root
        self.root.title("My AI - Local Assistant")
        self.root.geometry("900x700")
        self.root.minsize(650, 500)
        self.root.configure(bg=BG)

        self.messages = []
        self.events = queue.Queue()
        self.stop_event = threading.Event()
        self.busy = False
        self.current_reply = ""
        self.reply_widget = None
        self.closing = False

        self.build_ui()
        self.add_message(
            "assistant",
            "Welcome! I'm your local AI assistant. Ask me anything."
        )
        self.root.after(60, self.process_events)
        self.root.protocol("WM_DELETE_WINDOW", self.close_app)

    def build_ui(self):
        header = tk.Frame(self.root, bg=BG, height=66)
        header.pack(fill="x")
        header.pack_propagate(False)

        tk.Label(
            header, text="✦  My AI", bg=BG, fg=TEXT,
            font=("Segoe UI", 19, "bold")
        ).pack(side="left", padx=(22, 14))

        tk.Label(
            header, text="LOCAL · QWEN 2.5", bg=BG, fg=MUTED,
            font=("Segoe UI", 9)
        ).pack(side="left", pady=5)

        tk.Button(
            header, text="+ New chat", command=self.new_chat,
            bg=PANEL, fg=TEXT, activebackground="#383838",
            activeforeground=TEXT, relief="flat", bd=0,
            font=("Segoe UI", 10), padx=14, pady=9,
            cursor="hand2"
        ).pack(side="right", padx=18, pady=12)

        tk.Frame(self.root, bg="#333333", height=1).pack(fill="x")

        chat_area = tk.Frame(self.root, bg=BG)
        chat_area.pack(fill="both", expand=True, padx=12, pady=(10, 6))

        self.canvas = tk.Canvas(
            chat_area, bg=BG, highlightthickness=0, bd=0
        )
        scrollbar = tk.Scrollbar(
            chat_area, orient="vertical", command=self.canvas.yview
        )
        self.messages_frame = tk.Frame(self.canvas, bg=BG)
        self.messages_frame.bind(
            "<Configure>",
            lambda _e: self.canvas.configure(
                scrollregion=self.canvas.bbox("all")
            )
        )
        self.canvas_window = self.canvas.create_window(
            (0, 0), window=self.messages_frame, anchor="nw"
        )
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.bind(
            "<Configure>",
            lambda e: self.canvas.itemconfigure(
                self.canvas_window, width=e.width
            )
        )
        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.canvas.bind_all(
            "<MouseWheel>",
            lambda e: self.canvas.yview_scroll(
                int(-e.delta / 120), "units"
            )
        )

        composer = tk.Frame(self.root, bg=PANEL)
        composer.pack(fill="x", padx=16, pady=(4, 8))

        self.input_box = tk.Text(
            composer, height=3, wrap="word", bg=PANEL, fg=TEXT,
            insertbackground=TEXT, relief="flat", bd=0,
            font=("Segoe UI", 11), padx=12, pady=12
        )
        self.input_box.pack(
            side="left", fill="both", expand=True, padx=(4, 0), pady=4
        )
        self.input_box.bind("<Control-Return>", self.send_from_shortcut)

        controls = tk.Frame(composer, bg=PANEL)
        controls.pack(side="right", fill="y", padx=8, pady=8)

        self.send_button = tk.Button(
            controls, text="➤", command=self.send_message,
            bg="#ffffff", fg="#111111",
            activebackground="#dddddd", relief="flat", bd=0,
            font=("Segoe UI", 16, "bold"), width=3, cursor="hand2"
        )
        self.send_button.pack()

        self.stop_button = tk.Button(
            controls, text="■ Stop", command=self.stop_generation,
            bg="#4b2929", fg="#ffffff", activebackground="#603333",
            relief="flat", bd=0, font=("Segoe UI", 9),
            state="disabled", cursor="hand2"
        )
        self.stop_button.pack(pady=(7, 0))

        tk.Label(
            self.root,
            text="Local Ollama model · Ctrl+Enter to send",
            bg=BG, fg=MUTED, font=("Segoe UI", 8)
        ).pack(pady=(0, 10))

    def add_message(self, role, text):
        row = tk.Frame(self.messages_frame, bg=BG)
        row.pack(fill="x", padx=8, pady=7)

        is_user = role == "user"
        bubble_bg = USER_BUBBLE if is_user else PANEL
        bubble = tk.Frame(row, bg=bubble_bg)
        bubble.pack(
            side="right" if is_user else "left",
            anchor="e" if is_user else "w",
            padx=4
        )

        tk.Label(
            bubble, text="You" if is_user else "My AI",
            bg=bubble_bg, fg="#d8e8ff" if is_user else "#8fc7ff",
            font=("Segoe UI", 9, "bold"), anchor="w"
        ).pack(fill="x", padx=12, pady=(9, 2))

        body = tk.Text(
            bubble, wrap="word", bg=bubble_bg, fg=TEXT,
            font=("Segoe UI", 10), relief="flat", bd=0,
            padx=12, pady=(2, 10), width=65, height=1,
            cursor="arrow", state="normal"
        )
        body.insert("1.0", text)
        body.pack(fill="x")
        self.fit_text_height(body)
        body.configure(state="disabled")

        self.root.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self.canvas.yview_moveto(1.0)
        return body

    def fit_text_height(self, widget):
        widget.update_idletasks()
        count = widget.count("1.0", "end-1c", "displaylines")
        if count:
            # Keep the Text widget tall enough to show wrapped lines.
            widget.configure(height=max(1, min(5000, count[0])))

    def new_chat(self):
        if self.busy:
            messagebox.showinfo(
                "Please wait",
                "Stop the current response and wait for it to finish before starting a new chat."
            )
            return
        self.messages.clear()
        for child in self.messages_frame.winfo_children():
            child.destroy()
        self.current_reply = ""
        self.reply_widget = None
        self.add_message("assistant", "New chat started. What would you like to ask?")

    def send_from_shortcut(self, _event=None):
        self.send_message()
        return "break"

    def send_message(self):
        if self.busy:
            return
        prompt = self.input_box.get("1.0", "end-1c").strip()
        if not prompt:
            return

        self.input_box.delete("1.0", "end")
        self.add_message("user", prompt)
        self.messages.append({"role": "user", "content": prompt})

        self.current_reply = ""
        self.stop_event.clear()
        self.busy = True
        self.send_button.configure(state="disabled")
        self.stop_button.configure(state="normal", text="■ Stop")
        self.reply_widget = self.add_message("assistant", "Thinking…")

        threading.Thread(target=self.call_ollama, daemon=True).start()

    def call_ollama(self):
        payload = {
            "model": MODEL,
            "messages": self.messages.copy(),
            "stream": True
        }
        request = Request(
            OLLAMA_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )

        parts = []
        error = None

        try:
            with urlopen(request, timeout=300) as response:
                for raw_line in response:
                    if self.stop_event.is_set():
                        break
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line:
                        continue
                    data = json.loads(line)
                    piece = data.get("message", {}).get("content", "")
                    if piece:
                        parts.append(piece)
                        self.events.put(("token", piece))
                    if data.get("done"):
                        break
        except HTTPError as exc:
            try:
                detail = exc.read().decode("utf-8", errors="replace")
            except Exception:
                detail = str(exc)
            error = f"Ollama returned HTTP {exc.code}: {detail}"
        except (URLError, TimeoutError, OSError) as exc:
            error = (
                "Could not connect to Ollama. Make sure it is running.\n\n"
                f"Details: {exc}"
            )
        except Exception as exc:
            error = f"Unexpected error: {exc}"

        self.events.put((
            "done", "".join(parts), error, self.stop_event.is_set()
        ))

    def process_events(self):
        if self.closing:
            return

        # Batch tokens arriving in this 60 ms window. Updating the Text
        # widget once per batch avoids slowing down on long answers.
        new_text_parts = []
        done_event = None

        try:
            while True:
                event = self.events.get_nowait()
                if event[0] == "token":
                    new_text_parts.append(event[1])
                elif event[0] == "done":
                    done_event = event
        except queue.Empty:
            pass

        if new_text_parts:
            self.current_reply += "".join(new_text_parts)
            self.append_reply_text("".join(new_text_parts))

        if done_event:
            _, answer, error, stopped = done_event
            if error:
                self.set_reply_text(error)
                # Remove the unanswered user prompt from context on error.
                if self.messages and self.messages[-1]["role"] == "user":
                    self.messages.pop()
            elif stopped:
                if not self.current_reply:
                    self.set_reply_text("Generation stopped.")
                # Keep partial answer in history if there is one.
                if self.current_reply:
                    self.messages.append({
                        "role": "assistant", "content": self.current_reply
                    })
            else:
                final_answer = answer.strip() or "(No text returned.)"
                # Ensure the final display exactly matches the complete answer.
                self.set_reply_text(final_answer)
                self.messages.append({
                    "role": "assistant", "content": final_answer
                })

            self.busy = False
            self.send_button.configure(state="normal")
            self.stop_button.configure(state="disabled", text="■ Stop")

        self.root.after(60, self.process_events)

    def append_reply_text(self, text):
        if not self.reply_widget or not self.reply_widget.winfo_exists():
            return
        self.reply_widget.configure(state="normal")
        self.reply_widget.insert("end", text)
        self.fit_text_height(self.reply_widget)
        self.reply_widget.configure(state="disabled")
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self.canvas.yview_moveto(1.0)

    def set_reply_text(self, text):
        if not self.reply_widget or not self.reply_widget.winfo_exists():
            return
        self.reply_widget.configure(state="normal")
        self.reply_widget.delete("1.0", "end")
        self.reply_widget.insert("1.0", text)
        self.fit_text_height(self.reply_widget)
        self.reply_widget.configure(state="disabled")
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self.canvas.yview_moveto(1.0)

    def stop_generation(self):
        if self.busy:
            self.stop_event.set()
            self.stop_button.configure(state="disabled", text="Stopping…")

    def close_app(self):
        self.closing = True
        self.stop_event.set()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = LocalChatbot(root)
    root.mainloop()
