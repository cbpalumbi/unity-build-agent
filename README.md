
# DevFlow.ai 🧠🎮

**Natural Language-Powered Unity Build Automation**  
Built with the Google Agent Development Kit (ADK) for the 2025 Google ADK Hackathon

---

## 🌟 Overview

**DevFlow.ai** is an AI-powered multi-agent orchestration system for Unity development, enabling developers and artists to trigger complex tasks—like builds, asset previews, and Git operations via simple natural language prompts. Lets game developers easily play any version of the game they want without the need for local builds or repository management. Also supports a speedy asset bundle pipeline for testing new models in game, not just a preview - truly running in the game.  

>  “Build the latest version of the game on main.”  
>  “I want to preview my new model in the game.”

Whether you're a designer, gameplay engineer, or technical artist, DevFlow.ai abstracts away manual Git commands, Unity Editor configs, and remote cloud ops. It automates the boring so you can focus on the creative.

---

## Demo Video
📽️ Check out a walkthrough here: https://www.youtube.com/watch?v=frQN-aOUpBk

---

## Explore the Code
Main agent file is multi_tool_agent/agent.py. The repo also includes a local copy of the google-adk repo so I could modify the built-in web interface to add UI for build notifications. 

---

## 🔧 How It Works

###  Multi-Agent AI System (Python + ADK)
- **Root Agent (Unity Orchestrator)** interprets natural language and delegates to:
  - `VersionControlAgent`: Handles repo state, branch validation, commit resolution
  - `BuildAgent`: Publishes build requests to Pub/Sub, handles caching metadata
  - `AssetAgent`: Manages `.glb` uploads, triggers Unity asset bundle pipeline

###  Unity VM Build Runner (PowerShell + C#)
- Runs as a **Windows Service** using NSSM
- Listens for Pub/Sub messages to:
  - Checkout Git branch + commit
  - Run Unity in batchmode via custom C# scripts
  - Compress and upload builds to GCS
  - Process asset bundles and move them into runtime-loadable format
  - Publish status updates to Pub/Sub

###  Google Cloud Stack
- **Compute Engine**: Unity build VM (Windows Server)
- **Pub/Sub**: Async build/asset communication
- **Cloud Storage**: Build artifacts, asset bundles, cache store
- **Cloud Run**: Hosts the ADK agent system (containerized with Docker)
- **Vertex AI (Gemini)**: Natural language processing

---

## 🧪 Challenges & Engineering Wins

-  **Unity Cloud Licensing**: Solved Unity headless builds on Windows VM
-  **Robust Windows Service**: Built resilient message handling for long-running job queue
-  **Natural Language Precision**: Translated vague queries into structured Git + build instructions
-  **Signed URL Caching**: Enabled repeat builds to skip compilation and serve immediately
-  **Asset Streaming Pipeline**: Let artists preview `.glb` files without touching Unity locally
-  **ADK Web Frontend Hackery**: Patched internal ADK web files to add custom status panels
\---

## Architecture Diagram

---


## 🤝 Credits

Developed by Christabella Palumbi  
Built for the [Google Agent Development Kit Hackathon 2025](https://developers.google.com/agent-hackathon)  

---

## 📜 License

MIT License — feel free to fork, remix, and build on top!
