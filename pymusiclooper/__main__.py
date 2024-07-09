import logging

from pymusiclooper.cli import cli_main


def cli():
    try:
        print(">>>>>>> pymusiclooper <<<<<<<<")
        cli_main(prog_name="pymusiclooper")
    except Exception as e:
        logging.error(e)


if __name__ == "__main__":
    cli()
