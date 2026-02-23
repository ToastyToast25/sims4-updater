"""
CDN Manager entry point.

Usage:
    python -m cdn_manager
"""


def main():
    try:
        from .app import CDNManagerApp
    except ImportError:
        # PyInstaller standalone mode — relative import fails
        from cdn_manager.app import CDNManagerApp
    app = CDNManagerApp()
    app.mainloop()


if __name__ == "__main__":
    main()
