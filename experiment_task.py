"""The fixed task for experiment.py: the prompts every arm receives, and the checks run on the result.

The task is a small feature project on click 8.1.7 (a command-line library, about 10,000 lines of source).
Run inside a finished workspace to score it:  python experiment_task.py   (with PYTHONPATH=src)
"""
import sys

REPO_URL = "https://github.com/pallets/click.git"
REPO_TAG = "8.1.7"

# One prompt per step, sent in this order into one conversation. Questions and changes are mixed on
# purpose: questions make the model look around, which is where a project file or a map could help.
PROMPTS = [
    "Where in this repo is it decided whether an option's default value is shown in --help output? "
    "Answer with the file, the function and the condition. Do not change any code.",

    "Add an email parameter type to click. Class `EmailParamType` in src/click/types.py with name "
    "\"email\", an instance exported as `click.EMAIL`, and the class exported as `click.EmailParamType`. "
    "A value is valid when it has no whitespace, exactly one '@', a non-empty part before it, and after it "
    "a domain with at least one '.' and no empty label. A valid value is returned unchanged. An invalid "
    "value fails with the message `'<value>' is not a valid email address.`",

    "Add tests for click.EMAIL to the test suite, following how the existing type tests are written, "
    "and run them.",

    "Add a keyword argument `deprecated: bool = False` to click.Option. When it is True, the option's help "
    "text ends with `(DEPRECATED)`, and when the option is given on the command line click prints "
    "`DeprecationWarning: The option '<name>' is deprecated.` to stderr, where <name> is the option's "
    "`name` attribute. Nothing is printed when the option is not given. Include it in to_info_dict. Add tests.",

    "In at most 8 lines, explain the order in which an option's value is resolved (command line, "
    "environment variable, default_map, default) and name the function that implements it. No code changes.",

    "Add a keyword argument `sort_commands: bool = True` to click.Group. With False, list_commands returns "
    "the commands in the order they were added, and --help lists them in that order. Add a test.",

    "Add a read-only property `output_lines` to click.testing.Result: `output` split into lines, without "
    "line endings. Add a test. Then document this and the three earlier additions in CHANGES.rst under a "
    "new 'Unreleased' heading at the top.",

    "List every place in src/click where MissingParameter is raised or constructed: file, function, and "
    "in one phrase what triggers it. Do not change any code.",

    "Extend the Option `deprecated` argument so it also accepts a string. With `deprecated=\"use --new\"` "
    "the help text ends with `(DEPRECATED: use --new)` and the warning is "
    "`DeprecationWarning: The option '<name>' is deprecated. use --new`. `deprecated=True` keeps working "
    "as before. Add tests.",

    "Shell completion must not offer deprecated options: when completing an option name for a command, "
    "leave out options that are deprecated, the same way hidden options are left out. Add a test.",

    "Trace what happens between `CliRunner.invoke(cmd, args)` and the command's callback being called. "
    "Name each function on the path in order, with its file, in at most 12 lines. No code changes.",

    "Add a port parameter type: class `PortParamType` in src/click/types.py with name \"port\", an "
    "instance exported as `click.PORT`, and the class exported as `click.PortParamType`. It converts the "
    "value to an int and accepts 1 to 65535. Anything else fails with the message "
    "`'<value>' is not a valid port number.` Add tests.",

    "Document click.EMAIL and click.PORT in docs/api.rst next to the other types, and add everything you "
    "have added since the last CHANGES.rst edit to its 'Unreleased' section.",

    "click.Command already has its own `deprecated` argument. Compare how it behaves with your Option "
    "`deprecated` argument and list the differences a user would notice, in at most 8 lines. No code changes.",

    "Run the full test suite. Fix any test that fails because of your changes. Then list every file you "
    "changed, one line each.",
]


def checks():
    """Yield (name, passed) for each requirement in PROMPTS that can be checked by running code."""
    import click
    from click.testing import CliRunner

    def ok(fn):
        try:
            return bool(fn())
        except Exception:
            return False

    def bad_email(value):
        try:
            click.EMAIL.convert(value, None, None)
        except click.BadParameter as e:
            return "is not a valid email address" in e.format_message()
        return False

    yield "EMAIL accepts a valid address", ok(lambda: click.EMAIL.convert("a.b@mail.example.com", None, None) == "a.b@mail.example.com")
    yield "EMAIL rejects bad addresses", ok(lambda: all(map(bad_email, ("a@b", "a b@c.de", "@b.co", "a@@b.co", "a@b..co"))))
    yield "EmailParamType exported, name is email", ok(lambda: click.EmailParamType.name == "email")

    def cli(**kw):
        @click.command()
        @click.option("--old", is_flag=True, help="Old way.", **kw)
        def cmd(old):
            pass
        return cmd

    run = CliRunner(mix_stderr=False).invoke
    yield "deprecated option: help ends with (DEPRECATED)", ok(lambda: "(DEPRECATED)" in run(cli(deprecated=True), ["--help"]).output)
    yield "deprecated option: warns on stderr when used", ok(
        lambda: "DeprecationWarning: The option 'old' is deprecated." in run(cli(deprecated=True), ["--old"]).stderr)
    yield "deprecated option: silent when not used", ok(lambda: "Deprecat" not in run(cli(deprecated=True), []).stderr)
    yield "deprecated is in to_info_dict", ok(
        lambda: cli(deprecated=True).params[0].to_info_dict()["deprecated"] is True)

    def group(**kw):
        g = click.Group("g", **kw)
        for name in ("zeta", "alpha", "mid"):
            g.add_command(click.Command(name))
        return g

    yield "sort_commands=False keeps insertion order", ok(
        lambda: group(sort_commands=False).list_commands(None) == ["zeta", "alpha", "mid"])
    yield "commands are sorted by default", ok(lambda: group().list_commands(None) == ["alpha", "mid", "zeta"])

    @click.command()
    def two():
        click.echo("one")
        click.echo("two")

    yield "Result.output_lines", ok(lambda: CliRunner().invoke(two).output_lines == ["one", "two"])
    yield "CHANGES.rst has an Unreleased heading", ok(lambda: "Unreleased" in open("CHANGES.rst", encoding="utf-8").read()[:600])

    def msg(**kw):
        @click.command()
        @click.option("--old", is_flag=True, help="Old way.", **kw)
        @click.option("--new", is_flag=True)
        def cmd(old, new):
            pass
        return cmd

    yield "deprecated message: shown in help", ok(
        lambda: "(DEPRECATED: use --new)" in run(msg(deprecated="use --new"), ["--help"]).output)
    yield "deprecated message: in the warning", ok(
        lambda: "DeprecationWarning: The option 'old' is deprecated. use --new" in run(msg(deprecated="use --new"), ["--old"]).stderr)

    def completed(cmd):  # option names offered when the user has typed "--"
        return [item.value for item in cmd.shell_complete(click.Context(cmd), "--")]

    yield "completion leaves out deprecated options", ok(
        lambda: "--old" not in completed(msg(deprecated=True)) and "--new" in completed(msg(deprecated=True)))

    def bad_port(value):
        try:
            click.PORT.convert(value, None, None)
        except click.BadParameter as e:
            return "is not a valid port number" in e.format_message()
        return False

    yield "PORT converts a valid port", ok(
        lambda: click.PORT.convert("8080", None, None) == 8080 and click.PortParamType.name == "port")
    yield "PORT rejects bad ports", ok(lambda: all(map(bad_port, ("0", "65536", "http", "-1"))))
    yield "docs/api.rst lists EMAIL and PORT", ok(
        lambda: all(word in open("docs/api.rst", encoding="utf-8").read() for word in ("EMAIL", "PORT")))
    yield "CHANGES.rst mentions the port type", ok(
        lambda: any(word in open("CHANGES.rst", encoding="utf-8").read() for word in ("PortParamType", "click.PORT", "PORT``")))


if __name__ == "__main__":
    results = list(checks())
    for name, passed in results:
        if not passed:
            print("FAILED:", name, file=sys.stderr)
    print(f"{sum(p for _, p in results)}/{len(results)}")
