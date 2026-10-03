"""Entry point for the packaged desktop app (PyInstaller)."""
import multiprocessing

if __name__ == "__main__":
    multiprocessing.freeze_support()  # spawned Monte Carlo workers start here and must not open a window
    from ucsim.app import main

    main()
