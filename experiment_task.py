"""The fixed task for experiment.py: the prompts every arm receives, and the checks run on the result.

The task is a small feature project on click 8.1.7 (a command-line library, about 10,000 lines of source).
Run inside a finished workspace to score it:  python experiment_task.py   (with PYTHONPATH=src)
Add --long to score the 35-prompt task that the context-cap test uses.
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

# The long task: the 15 prompts above, then 20 more. It exists to push the conversation past 200,000 tokens,
# so the context cap can be tested (arms E and F in experiment.py). The "read ... from the first line to the
# last" prompts are reviews, the kind of step that fills a real session with file contents.
LONG_PROMPTS = PROMPTS + [
    "Read src/click/core.py from the first line to the last (the whole file, not a search). Check that your "
    "Option `deprecated` handling is consistent with how `hidden` is handled everywhere in that file. "
    "Report in at most 8 lines and fix any gap you find.",

    "A deprecated option must not be required: constructing a click.Option with both `required=True` and "
    "a truthy `deprecated` raises ValueError. Add a test.",

    "Add a percentage parameter type: class `PercentParamType` in src/click/types.py with name \"percent\", "
    "an instance exported as `click.PERCENT`, and the class exported as `click.PercentParamType`. It accepts "
    "a number from 0 to 100 with an optional trailing '%' and returns it as a float fraction (\"50%\" gives "
    "0.5, \"12.5\" gives 0.125). Anything else fails with the message `'<value>' is not a valid percentage.` "
    "Add tests.",

    "Read src/click/types.py from the first line to the last. Do your new types follow the conventions of "
    "the existing ones (name, repr, to_info_dict, how errors are raised)? Report in at most 8 lines and fix "
    "any difference.",

    "Add a read-only property `stderr_lines` to click.testing.Result, the same as `output_lines` but for "
    "`stderr`. Add a test.",

    "Read src/click/parser.py from the first line to the last. In at most 10 lines, explain how "
    "`--name=value`, `--name value` and `-abc` (combined short flags) are each parsed. No code changes.",

    "Let click.Command's `deprecated` argument also accept a string, like your Option argument. With "
    "`deprecated=\"use new\"` the help text shows `(Deprecated: use new)` where it showed `(Deprecated)`, and "
    "the warning is `DeprecationWarning: The command '<name>' is deprecated. use new`. `deprecated=True` "
    "keeps working as before. Add tests.",

    "Read tests/test_options.py and tests/test_types.py from the first line to the last. Are the tests you "
    "added placed and written like their neighbours? Report in at most 8 lines and fix what is not.",

    "The Option deprecation warning must also be printed when the option's value comes from an environment "
    "variable, and still not when it comes from a default. Add tests.",

    "Read src/click/shell_completion.py from the first line to the last. In at most 10 lines, explain how "
    "completions for an option's value (not its name) are produced. No code changes.",

    "Include `sort_commands` in the Group's to_info_dict. Add a test.",

    "Read src/click/testing.py from the first line to the last. In at most 10 lines, explain how CliRunner "
    "captures stdout and stderr and what `mix_stderr` changes. No code changes.",

    "Add a host name parameter type, following exactly the conventions you used for the email and port "
    "types (class name, `name`, exports, error message wording, tests). A value is valid when it is one or "
    "more labels separated by '.', each label made of letters, digits and hyphens, not empty, and not "
    "starting or ending with a hyphen. A valid value is returned unchanged.",

    "Read docs/options.rst from the first line to the last, then add a section to it on deprecated options, "
    "written like the sections around it, with one example.",

    "Read src/click/termui.py from the first line to the last. In at most 10 lines, say which functions "
    "decide whether colour codes are kept or stripped, and how. No code changes.",

    "Document the percent and host types in docs/api.rst next to the other types, and add everything you "
    "have added since the last CHANGES.rst edit to its 'Unreleased' section.",

    "Write a file NOTES.md in the repo root that lists every public name and every keyword argument you "
    "have added to click in this conversation, one per line, each with its exact error or warning message "
    "if it has one.",

    "Read src/click/decorators.py from the first line to the last. In at most 8 lines, explain how the "
    "keyword arguments of `@click.option` reach `Option.__init__`, and whether your `deprecated` argument "
    "needed any change there. No code changes.",

    "Run `git diff` and read all of it. List anything that is inconsistent between the features you added "
    "(naming, messages, tests, docs), in at most 10 lines, and fix it.",

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


def long_checks():
    """The checks above, plus the requirements of the 20 extra prompts in LONG_PROMPTS."""
    import click
    from click.testing import CliRunner

    yield from checks()

    def ok(fn):
        try:
            return bool(fn())
        except Exception:
            return False

    def raises(fn, error, text=""):
        try:
            fn()
        except error as e:
            return text in (e.format_message() if isinstance(e, click.ClickException) else str(e))
        return False

    def text(name):
        return open(name, encoding="utf-8").read()

    def percent(value):
        return click.PERCENT.convert(value, None, None)

    def host(value):  # the prompt does not fix the name, so HOST and HOSTNAME both count
        return (getattr(click, "HOST", None) or click.HOSTNAME).convert(value, None, None)

    run = CliRunner(mix_stderr=False).invoke
    yield "deprecated and required together raise ValueError", ok(lambda: raises(
        lambda: click.Option(["--x"], required=True, deprecated=True), ValueError))

    yield "PERCENT converts to a fraction", ok(
        lambda: (percent("50%"), percent("12.5"), percent("100")) == (0.5, 0.125, 1.0) and click.PercentParamType.name == "percent")
    yield "PERCENT rejects bad values", ok(
        lambda: all(raises(lambda: percent(v), click.BadParameter, "is not a valid percentage") for v in ("101", "-1", "abc", "%")))

    @click.command()
    def errs():
        click.echo("e1", err=True)
        click.echo("e2", err=True)

    yield "Result.stderr_lines", ok(lambda: run(errs).stderr_lines == ["e1", "e2"])

    def old(deprecated):
        return click.Command("old", callback=lambda: None, help="Do it.", deprecated=deprecated)

    yield "deprecated command message: in the warning", ok(
        lambda: "DeprecationWarning: The command 'old' is deprecated. use new" in run(old("use new"), []).stderr)
    yield "deprecated command message: in help", ok(
        lambda: "(Deprecated: use new)" in run(old("use new"), ["--help"]).output and "(Deprecated)" in run(old(True), ["--help"]).output)

    def from_env():
        @click.command()
        @click.option("--old", envvar="OLD_WAY", deprecated=True)
        def cmd(old):
            pass
        return cmd

    yield "deprecated option: warns when set by an environment variable", ok(
        lambda: "is deprecated" in run(from_env(), [], env={"OLD_WAY": "1"}).stderr and "Deprecat" not in run(from_env(), []).stderr)

    def info():
        g = click.Group("g", sort_commands=False)
        return g.to_info_dict(click.Context(g))

    yield "sort_commands is in the Group's to_info_dict", ok(lambda: info()["sort_commands"] is False)

    yield "HOST accepts valid names", ok(
        lambda: host("api.example-1.com") == "api.example-1.com" and host("localhost") == "localhost")
    yield "HOST rejects bad names, message worded like the other types", ok(
        lambda: all(raises(lambda: host(v), click.BadParameter, "is not a valid host") for v in ("a..b", "a b.com", "-a.com", "a_b.com")))

    yield "docs/options.rst covers deprecated options", ok(lambda: "deprecated" in text("docs/options.rst").lower())
    yield "docs/api.rst lists PERCENT and HOST", ok(lambda: all(w in text("docs/api.rst") for w in ("PERCENT", "HOST")))
    yield "CHANGES.rst mentions the later additions", ok(
        lambda: all(w in text("CHANGES.rst").lower() for w in ("percent", "host", "stderr_lines")))
    yield "NOTES.md lists what was added", ok(
        lambda: all(w in text("NOTES.md") for w in ("EMAIL", "PORT", "PERCENT", "HOST", "output_lines", "stderr_lines", "sort_commands", "deprecated")))


if __name__ == "__main__":
    results = list(long_checks() if "--long" in sys.argv else checks())
    for name, passed in results:
        if not passed:
            print("FAILED:", name, file=sys.stderr)
    print(f"{sum(p for _, p in results)}/{len(results)}")
