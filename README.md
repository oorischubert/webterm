# WebTerm

**AI-powered website assistant generator**

Scan any website and instantly create an AI assistant that can navigate and interact with it. Like Stripe for payments, but for AI agents on websites.

## 🔧 Key Tools

### Agent

The core AI assistant that orchestrates website navigation and interaction. The Agent class provides:

- **Smart Conversation Management**: Maintains context across interactions with persistent or temporary message history
- **Tool Integration**: Seamlessly connects with the ToolKit for website scanning, parsing, and navigation
- **Adaptive Execution**: Two interaction modes:
  - `spin()`: Multi-step task completion with automatic tool orchestration
  - `message()`: Single-turn interactions for quick queries
- **Error Handling**: Robust error recovery for tool failures and API issues

```python
from utility.agent import Agent

# Create an AI agent
agent = Agent()

# Multi-step website analysis
result = agent.spin("Analyze the website structure of example.com and describe its main sections")

# Quick single query
info = agent.message("What tools are available?", use_tools=True)
```

### SiteScannerTool

Scan any website and instantly create an AI assistant that can navigate and interact with it. Like Stripe for payments, but for AI agents on websites.

## 🎯 What It Does

WebTerm analyzes websites and creates intelligent assistants that can:

- Navigate website structures automatically
- Understand page layouts and interactive elements
- Help users find information and complete tasks
- Integrate into your app with just a few lines of code

## ⚡ Quick Start

```python
from utility.SiteScannerTool import SiteScannerTool

# Scan a website and build navigation tree
scanner = SiteScannerTool()
tree = scanner.sitePropogator("https://your-website.com", n=3)

# Your AI assistant now understands the site structure
assistant = create_assistant(tree)
```

## 🏗️ How It Works

1. **Website Scanning**: Intelligently crawls and maps website structure
2. **Content Extraction**: Filters out backend code, keeps only user-facing elements
3. **AI Integration**: Creates context-aware assistants using OpenAI
4. **Easy Integration**: Drop into your app with minimal code

## 📁 Core Components

```
webterm/
├── webterm.py           # Development server
├── webterm.html         # Application frontend
├── utility/
|   ├── agent.py         # WebTerm Agent
│   └── agentToolKit.py  # Agent toolkit
└── tests/               # Testing utilities
    ├── webParser.py     # HTML parsing and frontend filtering
    └── toolKitTest.py   # Agent tool use test
```

## � Key Tools

### SiteScannerTool

Maps website hierarchies and builds navigation trees for AI understanding.

### WebParser

Extracts only user-facing content (buttons, links, forms) while filtering out backend code.

### AI Agent Integration

Creates intelligent assistants that understand website context and can help users navigate.

### Page Description Tool

Allows setting semantic descriptions for pages to enhance AI understanding.

```python
# Set page context for better AI assistance
description_tool = PageDescriptionTool()
description_tool.set_page_description("Main product catalog with filtering options")
```

## 🎮 Development Server

```bash
python webterm.py
# Launches frontend webpage
# Starts local server at http://127.0.0.1:5050
# Console commands: clear, list, tree, refresh, quit
```

## 🧠 AI Assistant Creation

The WebTerm Agent creates intelligent assistants that understand:

- **Website Navigation Patterns**: Learns optimal pathways through site structures
- **Interactive Elements**: Identifies and interacts with buttons, forms, links, and dynamic content
- **Content Relationships**: Understands hierarchies and semantic connections between pages
- **User Intent**: Interprets goals and provides contextual guidance

### Agent Architecture

The Agent operates in two main modes:

1. **Spin Mode** (`agent.spin()`): For complex, multi-step tasks requiring tool orchestration
2. **Message Mode** (`agent.message()`): For quick, single-turn interactions

```python
# Complex website analysis workflow
agent = Agent()
analysis = agent.spin(
    "Scan the e-commerce site and create a product catalog summary",
    debug=True  # Show step-by-step execution
)

# Quick information retrieval
page_info = agent.message("What's on the current page?", use_tools=True)
```