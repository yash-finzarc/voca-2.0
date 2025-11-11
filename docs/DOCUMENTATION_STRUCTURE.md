# Documentation Structure

This document describes the organization of the VOCA project documentation.

## 📁 Folder Structure

```
docs/
├── README.md                           # Documentation index and navigation
├── STARTUP_GUIDE.txt                   # Quick startup guide
├── TWILIO_SETUP.md                     # Twilio initial setup
├── TWILIO_VOCA_SETUP.md                # Complete Twilio VOCA integration
├── TWILIO_IMPLEMENTATION_GUIDE.md      # Twilio implementation patterns
├── VOCA_ARCHITECTURE_EXPLANATION.md    # System architecture
├── FASTAPI_MIGRATION_NOTES.md          # Flask to FastAPI migration
├── NGROK_EXPLANATION.md                # ngrok explanation and usage
└── DOCUMENTATION_STRUCTURE.md          # This file
```

## 📚 Document Categories

### Getting Started
- **STARTUP_GUIDE.txt** - Complete startup guide with commands
- **TWILIO_SETUP.md** - Step-by-step Twilio setup
- **TWILIO_VOCA_SETUP.md** - Detailed Twilio VOCA integration

### Architecture & Design
- **VOCA_ARCHITECTURE_EXPLANATION.md** - Complete architecture overview
- **TWILIO_IMPLEMENTATION_GUIDE.md** - Implementation patterns

### Technical Guides
- **FASTAPI_MIGRATION_NOTES.md** - FastAPI migration guide
- **NGROK_EXPLANATION.md** - ngrok usage and explanation

## 🔗 Cross-References

All documentation files use relative paths for cross-referencing:
- References within `docs/` folder use relative paths (e.g., `[NGROK_EXPLANATION.md](NGROK_EXPLANATION.md)`)
- References to files outside `docs/` use relative paths (e.g., `[../README.md](../README.md)`)
- References to project files use relative paths (e.g., `[../requirements.txt](../requirements.txt)`)

## 📝 Maintenance

When adding new documentation:
1. Place files in the `docs/` folder
2. Update `docs/README.md` with the new document
3. Add cross-references as needed
4. Update this structure document if needed
5. Maintain consistent formatting across all documents

## 🎯 Documentation Standards

- Use Markdown (`.md`) for all documentation files
- Use plain text (`.txt`) only when necessary (e.g., STARTUP_GUIDE.txt)
- Include table of contents for long documents
- Use consistent heading styles
- Include code examples where applicable
- Add cross-references to related documents
- Keep documentation up-to-date with code changes

## 📖 Reading Order

### For New Users
1. Start with `STARTUP_GUIDE.txt`
2. Follow `TWILIO_SETUP.md`
3. Read `VOCA_ARCHITECTURE_EXPLANATION.md`

### For Developers
1. Read `VOCA_ARCHITECTURE_EXPLANATION.md`
2. Check `FASTAPI_MIGRATION_NOTES.md`
3. Review `TWILIO_IMPLEMENTATION_GUIDE.md`

### For Troubleshooting
1. Check `STARTUP_GUIDE.txt`
2. Review `NGROK_EXPLANATION.md`
3. See `TWILIO_VOCA_SETUP.md`

## 🔄 Updates

Last updated: 2025-11-11
- Organized all documentation into `docs/` folder
- Created documentation index (`docs/README.md`)
- Updated cross-references
- Added cross-reference from main README to docs folder

