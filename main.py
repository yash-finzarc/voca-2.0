#!/usr/bin/env python3
"""
Main entry point for VOCA application
"""
import sys
import os

# Add src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from voca.gui.app import VocaApp

def main():
    """Main application entry point."""
    app = VocaApp()
    app.run()

if __name__ == "__main__":
    main()
