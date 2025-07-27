# WebTerm

**AI-powered website assistant generator**

Scan any website and instantly create an AI assistant that can navigate and interact with it. Like Stripe for payments, but for AI agents on websites.

## 🔧 Key Tools

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
├── webParser.py              # HTML parsing and frontend filtering
├── agentServer.py           # Development server
├── utility/
│   ├── agentToolKit.py     # AI agent toolkit
│   └── SiteScannerTool.py  # Website structure mapping
└── tests/                  # Testing utilities
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
python agentServer.py
# Starts local server at http://127.0.0.1:5050
# Console commands: clear, list, quit
```

## 🧠 AI Assistant Creation

The toolkit generates assistants that understand:

- Website navigation patterns
- Interactive elements and their purposes
- Content relationships and hierarchies
- User intent and optimal pathways

Perfect for creating contextual help systems, automated navigation, and intelligent user guidance.
