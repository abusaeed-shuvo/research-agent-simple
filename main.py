import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from ddgs import DDGS
from dotenv import load_dotenv
from google import genai as google_genai
from openai import OpenAI
from rich.markdown import Markdown

from textual.app import App, ComposeResult
from textual.screen import Screen
from textual.widgets import Header, Footer, Input, RichLog, Static, OptionList
from textual.widgets.option_list import Option

import meta_ads
from logger import get_logger

logger = get_logger()

# --- Config ---
# Start LM Studio's local server first: LM Studio app -> Developer tab -> Start Server.
LMSTUDIO_BASE_URL = "http://localhost:1234/v1"
LMSTUDIO_API_KEY = "lm-studio"  # dummy, LM Studio doesn't check it

SAVE_DIR = Path.cwd() / "AI-search"

# .env lives right next to this script.
SCRIPT_DIR = Path(__file__).resolve().parent
load_dotenv(SCRIPT_DIR / ".env")

FB_ACCESS_TOKEN = os.getenv("FB_ACCESS_TOKEN")
FB_AD_ACCOUNT_ID = os.getenv("FB_AD_ACCOUNT_ID")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

client = OpenAI(base_url=LMSTUDIO_BASE_URL, api_key=LMSTUDIO_API_KEY)

gemini_client = google_genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None


def list_models():
    """Ask LM Studio which models are currently loaded/available."""
    lm_studio_failed = False
    try:
        models = client.models.list()
        model_list = sorted(m.id for m in models.data)
    except Exception as e:
        print(f"Could not reach LM Studio at {LMSTUDIO_BASE_URL}")
        print(f"  ({e})")
        lm_studio_failed = True
        model_list = []

    if GEMINI_API_KEY:
        model_list.append("gemini:gemini-3.5-flash")

    if lm_studio_failed and not GEMINI_API_KEY:
        print("Make sure LM Studio's local server is running:")
        print("  LM Studio app -> Developer tab -> Start Server")
        print("...and at least one model is loaded.")
        print("(Alternatively, set GEMINI_API_KEY in .env to use Gemini without LM Studio.)")
        sys.exit(1)

    return model_list


def search_web(query, max_results=5):
    results = []
    with DDGS() as ddgs:
        for r in ddgs.text(query, max_results=max_results):
            results.append({
                "title": r.get("title", ""),
                "url": r.get("href", ""),
                "content": r.get("body", ""),
            })
    return results


def fetch_text(url):
    try:
        response = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
    except requests.RequestException:
        return ""
    soup = BeautifulSoup(response.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer"]):
        tag.decompose()
    return soup.get_text(separator="\n", strip=True)


def generate_text(model_id: str, prompt: str) -> str:
    """Generate text using either Gemini (if model_id starts with 'gemini:') or LM Studio."""
    if model_id.startswith("gemini:"):
        stripped = model_id[len("gemini:"):]
        response = gemini_client.models.generate_content(
            model=stripped, contents=prompt
        )
        return response.text
    else:
        response = client.chat.completions.create(
            model=model_id,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content


def slugify(text, max_len=60):
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    text = re.sub(r"[\s_-]+", "-", text)
    return text[:max_len].strip("-") or "digest"


def timestamp_for_filename():
    # Colons aren't valid in Windows filenames, so use hyphens: HH-MM_DD-Mon-YYYY
    return datetime.now().strftime("%H-%M_%d-%b-%Y")


def ads_report_filename(period: str) -> Path:
    stamp = timestamp_for_filename()
    if period == "weekly":
        name = f"Meta-ads-report-weekly-{stamp}.md"
    else:
        name = f"Meta-ads-report-{stamp}.md"
    return SAVE_DIR / name


class ModelSelectScreen(Screen):
    """Shown only when more than one model is loaded in LM Studio."""

    CSS = """
    #prompt-label {
        margin: 1 2;
    }
    #model-list {
        margin: 0 2;
        border: round $accent;
    }
    """

    def __init__(self, models):
        super().__init__()
        self.models = models

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("Multiple models loaded in LM Studio — pick one (Enter to confirm):", id="prompt-label")
        yield OptionList(*[Option(m, id=m) for m in self.models], id="model-list")
        yield Footer()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.app.model = event.option.id
        self.app.push_screen(ResearchScreen())


class ResearchScreen(Screen):
    CSS = """
    #log {
        border: round $primary;
        padding: 1 2;
        margin: 1 2 0 2;
    }
    #status {
        color: $text-muted;
        margin: 0 3;
        height: 1;
    }
    #input-box {
        border: round $accent;
        margin: 0 2 1 2;
    }
    """

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield RichLog(id="log", markup=True, wrap=True, highlight=True)
        yield Static("", id="status")
        yield Input(placeholder="Ask a research question, or type /daily, /weekly, /exit", id="input-box")
        yield Footer()

    def on_mount(self) -> None:
        self.app.sub_title = f"model: {self.app.model}"
        log = self.query_one("#log", RichLog)
        log.write("[bold cyan]Local Research Agent[/bold cyan] — powered by LM Studio")
        log.write(f"[dim]Model: {self.app.model}[/dim]")
        log.write(f"[dim]Digests are saved to {SAVE_DIR}[/dim]")
        log.write("[dim]Commands: type a topic to research, or /daily, /weekly, /exit for Meta Ads reports[/dim]\n")
        self.query_one("#input-box", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        prompt = event.value.strip()
        if not prompt:
            return
        input_box = self.query_one("#input-box", Input)
        input_box.value = ""
        input_box.disabled = True

        log = self.query_one("#log", RichLog)
        log.write(f"\n[bold green]›[/bold green] {prompt}\n")

        normalized = prompt.lower().lstrip("/").strip()
        if normalized in ("exit", "quit", "q"):
            self.app.exit()
            return
        if normalized in ("daily", "ads daily", "ads-daily"):
            self.run_worker(lambda: self.handle_ads_report("daily"), exclusive=True, thread=True)
        elif normalized in ("weekly", "ads weekly", "ads-weekly"):
            self.run_worker(lambda: self.handle_ads_report("weekly"), exclusive=True, thread=True)
        else:
            self.run_worker(lambda: self.handle_research(prompt), exclusive=True, thread=True)

    def set_status(self, text: str) -> None:
        self.app.call_from_thread(self.query_one("#status", Static).update, text)

    def handle_research(self, prompt: str) -> None:
        log = self.query_one("#log", RichLog)
        model = self.app.model
        try:
            self.set_status("🔎 Searching the web...")
            results = search_web(prompt)

            pages = []
            for item in results:
                url = item.get("url")
                if not url:
                    continue
                self.set_status(f"🌐 Fetching: {url}")
                page_text = fetch_text(url)
                pages.append({
                    "title": item.get("title", ""),
                    "url": url,
                    "snippet": item.get("content", ""),
                    "page_text": page_text[:8000],
                })

            self.set_status("🧠 Thinking...")
            research_prompt = f"""User request:
{prompt}

Use these web results and page contents to answer in markdown format.

Data:
{json.dumps(pages, ensure_ascii=False)}
"""
            digest = generate_text(model, research_prompt)

            self.set_status("📝 Naming file...")
            name_response_text = generate_text(
                model,
                f"Give a short filename (3-6 words, lowercase, hyphen-separated, "
                f"no extension) summarizing this research topic: {prompt}. "
                f"Reply with ONLY the filename, nothing else.",
            )
            filename = slugify(name_response_text.strip())

            SAVE_DIR.mkdir(parents=True, exist_ok=True)
            filepath = SAVE_DIR / f"{filename}.md"
            counter = 1
            while filepath.exists():
                filepath = SAVE_DIR / f"{filename}-{counter}.md"
                counter += 1
            filepath.write_text(digest, encoding="utf-8")

            self.app.call_from_thread(log.write, Markdown(digest))
            self.app.call_from_thread(log.write, f"\n[dim]Saved to {filepath}[/dim]\n")
            self.set_status("Ready.")
        except Exception as e:
            self.app.call_from_thread(log.write, f"\n[bold red]Error:[/bold red] {e}\n")
            self.set_status("Error — see above.")
        finally:
            self.app.call_from_thread(self._reenable_input)

    def handle_ads_report(self, period: str) -> None:
        log = self.query_one("#log", RichLog)
        model = self.app.model
        try:
            if not FB_ACCESS_TOKEN or not FB_AD_ACCOUNT_ID:
                raise RuntimeError(
                    "FB_ACCESS_TOKEN / FB_AD_ACCOUNT_ID not found. Add them to a .env file "
                    f"in {SCRIPT_DIR} (see .env.example)."
                )

            days_back = 7 if period == "weekly" else 1
            label = "the last 7 days" if period == "weekly" else "today"

            logger.info("handle_ads_report  period=%s  days_back=%s", period, days_back)
            self.set_status("📊 Fetching Meta Ads data...")
            rows = meta_ads.build_report_dataset(FB_AD_ACCOUNT_ID, FB_ACCESS_TOKEN, days_back)
            logger.info("handle_ads_report  build_report_dataset returned %s rows", len(rows))

            if not rows:
                self.app.call_from_thread(
                    log.write, "\n[yellow]No active ads with data for this period.[/yellow]\n"
                )
                self.set_status("Ready.")
                return

            self.set_status("🧠 Summarizing performance...")
            ads_prompt = f"""You are a performance marketing analyst reviewing Meta (Facebook) Ads
data for {label}. Using the JSON data below, write a markdown report with:

1. An overview table: Ad name | Period spend | Budget type | Budget / Remaining | Cost per purchase
2. A short section flagging any ad whose cost-per-purchase is notably worse than the account average
   (or has spend but zero purchases)
3. A 3-5 sentence written summary of overall account health for this period

Notes on the data: "budget.type" is either "daily" (resets each day -- "remaining_today" is what's
left of today's budget) or "lifetime" (a running total across the campaign -- "remaining" is what
Meta reports as left). Amounts are in the ad account's currency's major unit.

Data:
{json.dumps(rows, ensure_ascii=False, default=str)}
"""
            digest = generate_text(model, ads_prompt)

            SAVE_DIR.mkdir(parents=True, exist_ok=True)
            filepath = ads_report_filename(period)
            filepath.write_text(digest, encoding="utf-8")

            self.app.call_from_thread(log.write, Markdown(digest))
            self.app.call_from_thread(log.write, f"\n[dim]Saved to {filepath}[/dim]\n")
            self.set_status("Ready.")
        except Exception as e:
            self.app.call_from_thread(log.write, f"\n[bold red]Error:[/bold red] {e}\n")
            self.set_status("Error — see above.")
        finally:
            self.app.call_from_thread(self._reenable_input)

    def _reenable_input(self) -> None:
        input_box = self.query_one("#input-box", Input)
        input_box.disabled = False
        input_box.focus()


class ResearchApp(App):
    TITLE = "Local Research Agent"
    BINDINGS = [("ctrl+c", "quit", "Quit")]

    def __init__(self):
        super().__init__()
        self.model = None

    def on_mount(self) -> None:
        models = list_models()
        if len(models) == 1:
            self.model = models[0]
            self.push_screen(ResearchScreen())
        else:
            self.push_screen(ModelSelectScreen(models))


if __name__ == "__main__":
    ResearchApp().run()
