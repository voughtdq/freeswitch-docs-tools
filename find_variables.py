import os, re, json, argparse, itertools, subprocess


class Source:
    def __init__(self, path, filename, line):
        self.path = path
        self.filename = filename
        self.line = line

    def __str__(self):
        return f"{self.full_path}:{self.line}"

    @property
    def full_path(self):
        return os.path.join(self.path, self.filename)

    def as_dict(self):
        return dict(path=self.path, filename=self.filename, line=self.line)


class Variable:
    def __init__(self, name):
        self.name = name
        self.sources = []

    def __str__(self):
        return f"{self.name}: {self.sources}"

    def add_source(self, path, filename, line):
        self.sources.append(Source(path, filename, line))

    def as_dict(self):
        return dict(
            name=self.name, sources=[source.as_dict() for source in self.sources]
        )


def has_ext(name, *args):
    return any(map(name.endswith, args))


class PathSpec:
    def __init__(self, directories=None, fn=None, cpp_match_fn=lambda x: []):
        # define argument dependencies

        self.cpp_match_fn = cpp_match_fn

        if directories and isinstance(directories, list):
            self.directories = directories
        else:
            raise ValueError("A directories argument must be provided")

        if fn:
            self.fn = fn
        else:
            raise ValueError("A fn argument must be provided")

        # setup our structures

        self.files = []
        self._constants = []  # we convert this to a dict when accessed publicly
        self._variables = []
        self._index = {}
        self.needs_review = []

        # initialization

        self._collect_files()
        self._recurse_and_find_constants()
        self._recurse_and_find_variables()
        self._make_index()

    def __iter__(self):
        return iter(self._variables)

    # Private

    # recursively collects a (dirpath, file,) tup for each file
    # encountered in each directory
    def _collect_files(self):
        walk = itertools.chain(*[os.walk(directory) for directory in self.directories])
        for dirpath, _, files in walk:
            self.files += [
                (
                    dirpath,
                    file,
                )
                for file in files
            ]

    def _recurse_and_find_constants(self):
        for dirpath, file in self.files:
            if has_ext(file, ".c", ".h", ".cpp", ".hpp"):
                self._constants += self._find_constants(dirpath, file)

    def _recurse_and_find_variables(self):
        for dirpath, file in self.files:
            if has_ext(file, ".c", ".cpp"):
                self._variables += self._find_variables(dirpath, file)

    def _find_constants(self, path, filename):
        file = os.path.join(path, filename)
        with open(file, "r", errors="ignore") as f:
            return self.cpp_match_fn(
                (
                    f,
                    filename,
                )
            )

    def _find_variables(self, path, filename):
        file = os.path.join(path, filename)
        with open(file, "r", errors="ignore") as f:
            return self.fn(
                (
                    f,
                    path,
                    filename,
                )
            )

    def _maybe_replace_with_constant(self, variable):
        if variable in self.constants.keys():
            variable = self.constants[variable]
        return variable
    
    def _make_index(self):
        for path, filename, line, variable in self._variables:
            variable = self._maybe_replace_with_constant(variable)

            if '"' in variable:
                variable = variable.replace('"', "")
            else:
                self.needs_review += [
                    (
                        path,
                        filename,
                        line,
                        variable,
                    )
                ]
                continue

            self._add_to_index(path, filename, line, variable)

    def _add_to_index(self, path, filename, line, variable):
        if variable not in self._index.keys():
            self._index[variable] = Variable(variable)

        self._index[variable].add_source(path, filename, line)

    # Public

    @property
    def index(self):
        return self._index

    @property
    def constants(self):
        return dict(self._constants)

    @property
    def variables(self):
        return self._variables

    @property
    def variables_with_replacements(self):
        "Prints out information about how variables were expanded."
        for _path, _filename, _line, variable in self._variables:
            if '"' not in variable:
                try:
                    const = self.constants[variable]
                    print(f"\n{variable} -> {const}")
                except:
                    print(f"\nwarning: {variable} has no expansion\n")
            else:
                print(variable)


def match_variable_line(expression, base):
    def matcher(tup):
        f, path, filename = tup
        found = []
        for i, line in enumerate(f):
            match = re.search(expression, line)
            if match is not None:
                variable = match.group("variable")
                variable = variable.split(")")[0]
                variable = variable.split()[0]
                src_path = path.replace(base, "")[1:]
                found.append(
                    (
                        src_path,
                        filename,
                        i + 1,
                        variable,
                    )
                )
        return found

    return matcher


def match_preprocessor_define(expression):
    def matcher(tup):
        f, filename = tup
        found = []
        for line in f:
            match = re.search(expression, line)
            if match is not None:
                const = match.group("const")
                val = match.group("val")
                found.append(
                    (
                        const,
                        val,
                    )
                )
        return found

    return matcher


var_expr = r"(switch_channel_var_(true|false)|switch_channel_(get|set)_variable\w*)(\(\w+[\-*\>*\w*]*\,\s*(?P<variable>\"*\w+\"*))"
cpp_expr = r"#define (?P<const>.+) (?P<val>.+)"


def get_version(p):
    process = subprocess.run(
        ["git", "describe", "--tags"], cwd=p, text=True, stdout=subprocess.PIPE
    )
    return process.stdout.strip()


def needs_review_report(needs_review):
    for path, filename, line, variable in needs_review:
        p = os.path.join(path, filename)
        print(f"{p}:{line} {variable}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="""
        Example:
        
        find_variables.py --base /path/to/freeswitch/project
        """
    )
    parser.add_argument(
        "--base",
        action="store",
        help="The base path to the FreeSWITCH project.",
        required=True,
    )
    parser.add_argument(
        "--dir",
        action="extend",
        nargs="+",
        type=str,
        help="Specify one or more directories relative to the base path to traverse. Defaults to the 'src' directory if both --dir and --exclude-src are not used.",
        default=["src"],
    )
    parser.add_argument(
        "--exclude-src",
        action="store_true",
        help="Pass this switch if you want to exclude the src directory from traversal.",
    )
    parser.add_argument(
        "--out",
        action="store",
        default="variables.json",
        help="The file in which to save the output. Defaults to 'variables.json'.",
    )
    parser.add_argument(
        "--needs-review",
        action="store_true",
        help="Prints a report of variables that need manual review.",
    )
    parser.add_argument(
        "--show-replacements",
        action="store_true",
        help="Prints a report with how "
    )

    args = parser.parse_args()
    base = args.base
    dirs = args.dir
    
    if args.exclude_src:
        dirs = filter(lambda d: d != "src", dirs)

    pathspec = PathSpec(
        directories=[os.path.join(base, p) for p in dirs],
        fn=match_variable_line(var_expr, base),
        cpp_match_fn=match_preprocessor_define(cpp_expr),
    )

    index = [pathspec.index[key] for key in sorted(pathspec.index, key=str.lower)]

    if args.show_replacements:
        pathspec.variables_with_replacements()

    if args.needs_review:
        needs_review_report(pathspec.needs_review)

    if pathspec.needs_review:
        count = len(pathspec.needs_review)
        word = "variable" if count == 1 else "variables"
        print(f'{count} {word} must be manually checked. Rerun with --needs-review to check.')
    
    count = len(pathspec.index)
    word = "variable" if count == 1 else "variables"
    outp = os.path.abspath(args.out)
    print(f'{count} {word} processed and output to {outp}')

    current_version = get_version(base)
    vs = dict(variables=[var.as_dict() for var in index], version=current_version)

    with open(args.out, "w") as f:
        f.write(json.dumps(vs))
