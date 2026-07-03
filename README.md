# Local Research Agent

A terminal-based TUI application for web research and Meta/Facebook Ads performance reporting, powered by local LLMs via LM Studio.

![Demo](https://img.shields.io/badge/TUI-Textual-blue)
![Python](https://img.shields.io/badge/python-3.8+-blue)
![License](https://img.shields.io/badge/license-MIT-green)

## Features

- **Web Research**: Ask questions and get AI-generated markdown summaries from web search results
- **Meta Ads Reports**: Generate performance reports for your Facebook/Meta ad campaigns
- **Local LLM Support**: Uses LM Studio for private, offline AI inference
- **Optional Gemini**: Can also use Google's Gemini API as an alternative
- **TUI Interface**: Clean terminal interface built with Textual
- **Auto-saved Digests**: All research and reports saved as markdown files

## Demo

### Meta Ads Report Example

| Ad Name | Period Spend | Budget Type | Cost per Purchase |
| :--- | :---: | :---: | :---: |
| Adset - 1 / Design 1 | 0.09 | Daily | 0.03 |
| Adset - 1 / Design 2 | 3.35 | Daily | 0.22 |

The agent generates comprehensive reports with:
- Overview tables with spend, budget, and performance metrics
- Performance flags highlighting underperforming ads
- Account health summaries with actionable insights

## Requirements

- **Python 3.8+**
- **LM Studio** (recommended) - Download from [lmstudio.ai](https://lmstudio.ai)
  - Or **Google Gemini API key** (optional alternative)
- **Meta/Facebook Access Token** (for ads reports)

## Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/research-agent-simple.git
   cd research-agent-simple
   ```

2. **Create a virtual environment**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables**
   ```bash
   cp .env.example .env
   # Edit .env with your credentials
   ```

## Configuration

### LM Studio (Required for local inference)

1. Download and install [LM Studio](https://lmstudio.ai)
2. In LM Studio, go to the **Developer** tab
3. Click **Start Server**
4. Download and load at least one model (e.g., Llama 3, Mistral)

### Environment Variables (.env)

```env
# Meta (Facebook) Marketing API
# Get your access token from Meta Developer Console with ads_read permission
FB_ACCESS_TOKEN=your_long_lived_access_token_here
FB_AD_ACCOUNT_ID=act_XXXXXXXXXXXXX

# Google Gemini API (optional)
# Get a free API key at: https://aistudio.google.com/apikey
# GEMINI_API_KEY=your_gemini_api_key_here
```

## Usage

### Start the Application

```bash
python main.py
```

### Commands

| Command | Description |
|---------|-------------|
| `your question here` | Research any topic - searches the web and generates a markdown summary |
| `/daily` | Generate a Meta Ads report for today |
| `/weekly` | Generate a Meta Ads report for the last 7 days |
| `/exit` or `/quit` | Exit the application |

### Example Session

```
$ python main.py

[bold cyan]Local Research Agent[/bold cyan] — powered by LM Studio
[dim]Model: llama-3.2-3b-instruct[/dim]
[dim]Digests are saved to AI-search[/dim]
[dim]Commands: type a topic to research, or /daily, /weekly, /exit for Meta Ads reports[/dim]

› What are the benefits of meditation?

🔎 Searching the web...
🌐 Fetching: https://example.com/meditation-benefits
🧠 Thinking...
📝 Naming file...

# Benefits of Meditation

Meditation offers numerous benefits including...

[dim]Saved to AI-search/benefits-of-meditation.md[/dim]
```

## Output

All research digests and reports are saved to the `AI-search/` directory:

- **Research topics**: `AI-search/{topic-slug}.md`
- **Daily reports**: `AI-search/Meta-ads-report-{timestamp}.md`
- **Weekly reports**: `AI-search/Meta-ads-report-weekly-{timestamp}.md`

## Project Structure

```
research-agent-simple/
├── main.py           # Main TUI application
├── meta_ads.py       # Meta Marketing API helpers
├── logger.py         # Structured logging
├── requirements.txt  # Python dependencies
├── .env.example      # Environment variable template
├── .gitignore        # Git ignore rules
└── AI-search/        # Output directory (gitignored)
    └── *.md          # Generated research digests and reports
```

## Dependencies

- `textual` - TUI framework
- `openai` - LM Studio API client
- `requests` - HTTP requests
- `beautifulsoup4` - HTML parsing
- `ddgs` - DuckDuckGo search
- `python-dotenv` - Environment variable loading
- `google-genai` - Gemini API client (optional)

## Troubleshooting

### LM Studio not connecting?
- Make sure LM Studio is running
- Check that the server is started in the Developer tab
- Ensure at least one model is loaded

### Meta Ads API errors?
- Verify your `FB_ACCESS_TOKEN` is valid and not expired
- Check that `FB_AD_ACCOUNT_ID` includes the `act_` prefix
- Ensure your token has the `ads_read` permission

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
