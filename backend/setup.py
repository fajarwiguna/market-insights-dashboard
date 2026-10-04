"""Bundle canonical SQL migrations inside the installed Python package."""

from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py


class BuildWithMigrations(build_py):
    def run(self):
        super().run()
        migrations = sorted((Path(__file__).parent / "migrations").glob("*.sql"))
        if not migrations:
            raise RuntimeError("Tidak ada migrasi SQL untuk dimasukkan ke package.")
        destination = Path(self.build_lib) / "market_report" / "migrations"
        destination.mkdir(parents=True, exist_ok=True)
        for source in migrations:
            self.copy_file(str(source), str(destination / source.name))


setup(cmdclass={"build_py": BuildWithMigrations})
