---
mode: agent
---
Define the task to achieve, including specific requirements, constraints, and success criteria.
You are to create a Python-based application and set of tools for live detection of the 5min break and re-test strategy from Scarface Trades. The capability comes with a comprehensive back-testing tool and way to visualize test and simulated trade results. For more details consult the Markdown documentation in this project. The ultimate goal is to produce a robust, well-documented, and user-friendly package that traders can use to receive real-time high-quality trade signals based on the Scarface break and re-test strategy.

Additional instructions:
1. Wait for Explicit Commit Request
Never automatically commit code or suggest git commit commands
Always wait for you to explicitly ask me to commit before presenting any git commands
Only show commit-related actions when you request them
2. No Summary Markdown Files
Do not create new markdown files to document changes or summarize work
Exception: Only create documentation files if you specifically request it
Keep documentation updates to existing files when needed
3. Use Tools Instead of Suggesting Commands
Use the edit tool instead of printing code blocks with file changes
Use the run_in_terminal tool instead of printing commands for you to run
Don't mention tool names to you (e.g., say "I'll run the command in a terminal" instead of "I'll use the run_in_terminal tool")
Take direct action rather than suggesting what you should do
4. Context-First Approach
Gather context before making changes
Read relevant files to understand the codebase
Understand existing structure and patterns
Validate understanding before implementing
Don't make assumptions - verify first
5. Don't worry about backward compatibility, just keep the codebase clean and self-consistent
6. Unit tests should be run in areas of changes after updates are made. In general, each Python file should have it's own unit test and have >= 80% test coverage.
7. When I ask to run pre-commit, checks this includes unit tests, linting, code coverage, functional tests
8. Maintain all main s/w dev workflow operations in the Makefile. Prefer running these workflow operations using "make" operations over running specific commands unless specific commands are warranted.
9. Over-arching tasks that we're working on are in todo.md
10. Start Terminal commands by default in ~/Development/python/break-and-retest folder in a Python venv. Files referenced here should be assumed to be relative to this project folder.
11. Maintain a history of what we've worked on in each chat thread in the context_summary.md
12. Use the Markdown documents in this project for specifications (*.md files in this project) when you don't have enough information, and if you still can't find the info you're looking for ask me when in doubt.
13. Before making any code changes first explain to me why you want to make them and how they will improve the code. Let me give the "okay" before you make the code changes.
14. Do not use parenthesis characters in MermaidJS diagrams, they cause syntax errors.

Core Theme
Take action directly using tools, wait for explicit approval on commits, and don't create unnecessary documentation files.
