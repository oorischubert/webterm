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

### Assistant

A specialized AI assistant that provides site-specific question answering grounded in website structure. The Assistant class offers:

- **Site-Grounded Responses**: Always stays within the context of the analyzed website
- **SiteTree Integration**: Uses complete website structure for accurate, contextual answers
- **Conversation Memory**: Maintains chat history for natural, multi-turn conversations
- **Focused Expertise**: Refuses off-topic queries to maintain website focus

```python
from utility.assistant import Assistant
from utility.agentToolKit import SiteTree

# Load a pre-scanned website structure
tree = SiteTree().load("website_structure.json")

# Create a site-specific assistant
assistant = Assistant(tree)

# Ask questions about the website
response = assistant.answer("What are the main sections of this website?")
print(response)

# Follow-up questions maintain context
followup = assistant.answer("Tell me more about the products section")
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

### Drop-in Chatbot Widget

Add an AI-powered chat widget to any website with just one line:

```html
<script src="http://<server_ip>:5050/webterm.js" defer></script>
```

The widget automatically:

- Injects Tailwind CSS and FontAwesome if not present
- Creates a floating chat interface with glassmorphism design
- Provides a responsive, accessible chat experience
- Can be positioned on left or right side of the screen

### Programmatic Usage

```python
from utility.SiteScannerTool import SiteScannerTool

# Scan a website and build navigation tree
scanner = SiteScannerTool()
tree = scanner.sitePropogator("https://your-website.com", n=3)

# Your AI assistant now understands the site structure
assistant = Assistant(tree)
```

## 🏗️ How It Works

1. **Website Scanning**: Intelligently scans and maps website structure
2. **Content Extraction**: Filters out backend code, keeps only user-facing elements
3. **AI Integration**: Creates context-aware assistants using OpenAI
4. **Easy Integration**: Drop into your app with minimal code

## 📁 Core Components

```
webterm/
├── webterm.py           # Development server
├── webterm.html         # Application frontend
├── webterm.js           # Drop-in chat widget
├── utility/
│   ├── agent.py         # WebTerm Agent
│   ├── assistant.py     # WebTerm site assistant
│   └── agentToolKit.py  # Agent toolkit
└── tests/
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

### WebTerm Chat Widget

A plug-and-play chat interface that can be embedded on any website with zero configuration:

```html
<!-- Just add this one line to your HTML -->
<script src="http://<server_ip>:5050/webterm.js" defer></script>
```

**Features:**

- **Zero Dependencies**: Automatically injects required CSS/JS (Tailwind, FontAwesome)
- **Responsive Design**: Works seamlessly on desktop and mobile
- **Glassmorphism UI**: Modern frosted glass aesthetic with backdrop blur
- **Configurable Position**: Can dock to left or right corner
- **Accessibility**: Keyboard navigation and screen reader friendly

**Customization Options:**

- Position: Set `POSITION` to "left" or "right" in the script
- Styling: Built with Tailwind classes for easy theme modification
- Integration: Ready to connect with WebTerm backend APIs

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
# Console commands: clear, list, tree, save, refresh, quit
```

## 🧠 AI Assistant Creation

The WebTerm Agent creates intelligent assistants that understand:

- **Website Navigation Patterns**: Learns optimal pathways through site structures
- **Interactive Elements**: Identifies and interacts with buttons, forms, links, and dynamic content
- **Content Relationships**: Understands hierarchies and semantic connections between pages
- **User Intent**: Interprets goals and provides contextual guidance

### Agent Architecture

The WebTerm system uses two complementary AI components:

1. **Agent** (`agent.py`): General-purpose AI that can use tools and orchestrate complex workflows

   - **Spin Mode**: For complex, multi-step tasks requiring tool orchestration
   - **Message Mode**: For quick, single-turn interactions

2. **Assistant** (`assistant.py`): Site-specific AI that provides focused, grounded responses
   - Always stays within the context of a specific website's SiteTree
   - Maintains conversation history for natural multi-turn discussions
   - Refuses off-topic queries to maintain focus

```python
# Agent: Complex website analysis workflow
agent = Agent()
analysis = agent.spin(
    "Scan the e-commerce site and create a product catalog summary",
    debug=True  # Show step-by-step execution
)

# Assistant: Site-specific Q&A
tree = SiteTree().load("scanned_site.json")
assistant = Assistant(tree)
info = assistant.answer("What products are available on this site?")
```
