"""
CDN Manager entry point.

Usage:
    python -m cdn_manager
"""


def _patch_ctk_negative_pad():
    """Workaround for CustomTkinter + Python 3.14 incompatibility.

    Python 3.14's tkinter rejects negative pad values (-1) that
    CTkSegmentedButton uses internally. Monkey-patch to use 0 instead.
    """
    try:
        from customtkinter.windows.widgets.ctk_segmented_button import CTkSegmentedButton

        _orig = CTkSegmentedButton._create_button_grid

        def _patched(self):
            try:
                _orig(self)
            except Exception:
                # Fallback: re-grid buttons with padx=0
                for index, (_value, button) in enumerate(self._buttons_dict.items()):
                    if index == 0:
                        button.grid(row=0, column=index, sticky="nsew")
                    else:
                        button.grid(row=0, column=index, sticky="nsew", padx=(0, 0))

        CTkSegmentedButton._create_button_grid = _patched
    except Exception:
        pass


def main():
    _patch_ctk_negative_pad()
    try:
        from .app import CDNManagerApp
    except ImportError:
        # PyInstaller standalone mode — relative import fails
        from cdn_manager.app import CDNManagerApp
    app = CDNManagerApp()
    app.mainloop()


if __name__ == "__main__":
    main()
