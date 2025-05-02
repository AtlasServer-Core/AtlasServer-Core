<!-- Hero Section -->
<div align="center">

  <!-- Logo -->
  <div align="center" style="background-color: #000; padding: 1em; display: inline-block; border-radius: 8px;">
     <img
       src="app/static/svg/atlas.svg"
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

---

### 🚀 Quick Start

```bash
# Clone the repository
git clone https://github.com/AtlasServer-Core/AtlasServer-Core.git
cd AtlasServer-Core

# Install AtlasServer
pip install .

# Start the server
atlasserver start

# List all applications
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

---


### 📢 Join the Beta

We’re running a **3–4 week closed beta** to refine usability, tunnel stability, and overall workflow.

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

## 💖 Support the Project

If you find AtlasServer-Core useful, please consider buying me a coffee:

[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-ffdd00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black)](https://buymeacoffee.com/atlasserver)
