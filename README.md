<!-- Hero Section -->
<div align="center">

  <!-- Logo -->
  <div align="center" style="background-color: #000; padding: 1em; display: inline-block; border-radius: 8px;">
     <img
       src="https://atlasserver.vercel.app/static/svg/atlas.svg"
       alt="AtlasServer Logo"
       width="200"
       style="display: block;"
     />
   </div>


  <!-- Main Title -->
  <h1 style="margin-top: 0.5em; font-size: 3rem; color: #2d3748;">
    AtlasServer‑Core
  </h1>

  <!-- Tagline -->
  <p style="font-size: 1.25rem; color: #4a5568; line-height: 1.5;">
    💻 <strong>Fast deploy. No cloud. Just code.</strong><br />
    <em>From developers to developers.</em>
  </p>

  <!-- PyPI and GitHub Badges -->
  <p align="center">
    <a href="https://pypi.org/project/atlasserver/"><img src="https://img.shields.io/pypi/v/atlasserver.svg" alt="PyPI Version"></a>
    <a href="https://pypi.org/project/atlasserver/"><img src="https://img.shields.io/pypi/pyversions/atlasserver.svg" alt="Python Versions"></a>
    <a href="https://pypi.org/project/atlasserver/"><img src="https://img.shields.io/pypi/dm/atlasserver" alt="PyPI Downloads"></a>
    <a href="https://github.com/AtlasServer-Core/AtlasServer-Core/"><img src="https://img.shields.io/github/stars/AtlasServer-Core/AtlasServer-Core.svg" alt="GitHub Stars"></a>
    <a href="https://github.com/AtlasServer-Core/AtlasServer-Core/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-Apache_2.0-blue.svg" alt="License"></a>
    <a href="https://github.com/AtlasServer-Core/AtlasServer-Core/"><img src="https://img.shields.io/endpoint?url=https://atlas-api-kl.onrender.com/stats/AtlasServer-Core/AtlasServer-Core/clones" alt="Clones"></a>
  </p>

  <p align="center">
    <img
      src="https://res.cloudinary.com/dmtomxyvm/image/upload/v1746656451/sprrvldk6kn4udtfuq3m.png"
      alt="AtlasServer Dashboard"
      width="80%"
    />
  </p>

  <!-- Divider -->
  <hr style="width: 50px; border: 2px solid #2d3748; margin: 1.5em auto;" />

</div>




### ⚙️ Current Features

- **Supported frameworks**: `Flask`, `FastAPI`, `Django` and `Django REST Framework`
- **Tunneling**: Support for `Ngrok`
- **Admin panel**: Basic web interface to manage applications
- **App management**: Start, stop, and delete applications from the panel
- **Command Line Interface**: Manage server and applications from the terminal
- **Authentication**: Basic authentication system with limited roles
- **AI-powered deployment**: Intelligent project analysis and deployment suggestions

---

### 🚀 Quick Start

```bash
# Install AtlasServer from PyPI
pip install atlasserver

# Optional: Install AI capabilities
pip install atlasai-cli

# Start the server
atlasserver start

# Access the web interface at http://localhost:5000
# Default credentials: Create your own admin account on first run

# List all applications from CLI
atlasserver app list
```

### 💻 CLI Commands

AtlasServer includes a powerful CLI for easier management:

```bash
# Server management
atlasserver start    # Start the server
atlasserver stop     # Stop the server
atlasserver status   # Check server status

# Application management
atlasserver app list           # List all applications
atlasserver app start APP_ID   # Start an application
atlasserver app stop APP_ID    # Stop an application
atlasserver app restart APP_ID # Restart an application
atlasserver app info APP_ID    # Show application details
```

#### Optional AI Commands (requires atlasai-cli)

```bash
# AI configuration
atlasserver ai setup --model llama3:8b      # Configure with local Ollama model
atlasserver ai setup --provider openai --model gpt-4.1 --api-key YOUR_KEY  # Use OpenAI

# Project analysis
atlasserver ai suggest ~/path/to/your/project     # Get deployment suggestions
atlasserver ai suggest ~/my-project --language es # Get suggestions in Spanish

# General AI queries
atlasai --query "What files are in this project?"                     # Simple query
atlasai --query "How can I deploy this Express app?" --language es    # Query in Spanish
atlasai --query "Compare this project's dependencies with best practices"  # Complex analysis
```

### 🤖 AI-Powered Deployment (Optional)

AtlasServer supports intelligent project analysis through the optional **AtlasAI-CLI** package:

- **Smart project detection**: Automatically identifies Flask, FastAPI, Django and other frameworks
- **Contextual recommendations**: Suggests appropriate commands, ports, and environment variables
- **Interactive exploration**: Analyzes project structure and key files
- **Multilingual support**: Get explanations in English or Spanish
- **General AI queries**: Ask anything about your system, projects, or development needs

**Installation:**
```bash
# Install the optional AI capabilities
pip install atlasai-cli

# Alternatively, install both AtlasServer and AI capabilities
pip install atlasserver atlasai-cli
```

**Requirements:**
- [Ollama](https://github.com/ollama/ollama) for running local AI models
- Alternatively, OpenAI API for cloud-based models

**Setup:**
```bash
# Install and start Ollama (for local models)
ollama serve

# Pull your preferred model
ollama pull llama3:8b

# Configure AtlasServer AI
atlasserver ai setup --model llama3:8b

# Analyze a project
atlasserver ai suggest ~/path/to/your/project

# Make a general query about your system or projects
atlasai --query "What projects do I have here and how should I deploy them?"
```

### 🔧 Development Installation

If you want to contribute to AtlasServer or install from source:

```bash
# Clone the repository
git clone https://github.com/AtlasServer-Core/AtlasServer-Core.git
cd AtlasServer-Core

# Install in development mode
pip install -e .
```

---


### 📢 Join the Beta

We're running a **3–4 week closed beta** to refine usability, tunnel stability, and overall workflow.

👉 **Join our Discord** for beta access, discussions, and direct feedback:

[![Discord](https://img.shields.io/badge/Join%20Beta%20Discord-7289DA?style=for-the-badge&logo=discord&logoColor=white)](https://discord.gg/QedUbbQpK9)

---


### 📄 License

This project is licensed under the **Apache License 2.0**. 
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://www.apache.org/licenses/LICENSE-2.0)

You may obtain a copy of the License at:  
`http://www.apache.org/licenses/LICENSE-2.0`

Unless required by applicable law or agreed to in writing, software  
distributed under the License is distributed on an **"AS IS" BASIS**,  
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. 

See the [full license text](LICENSE) for details. 

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=AtlasServer-Core/AtlasServer-Core&type=Date)](https://www.star-history.com/#AtlasServer-Core/AtlasServer-Core&Date)

### 💖 THANK YOU FOR YOUR STARS!!


## 💖 Support the Project

If you find AtlasServer-Core useful, please consider buying me a coffee:

[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-ffdd00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black)](https://buymeacoffee.com/atlasserver)
