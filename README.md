# curlbot_v2


# Development environment

## Pyenv

We use pyenv to manage the python version separately from the global python and avoid messing up any other environments.

### Install `zlib` and `pyenv`.

On mac:

```sh
brew install zlib
brew install pyenv
```

Then add these lines to your shell startup file (any platform):

```sh
eval "$(pyenv init -)"
eval "$(pyenv init --path)"
```

### Install python

```sh
export LDFLAGS="-L/usr/local/opt/zlib/lib"  # Only needed for mac
export CPPFLAGS="-I/usr/local/opt/zlib/include"  # Only needed for mac
pyenv install 3.10.10
```

## Poetry

We use poetry to manage Python package dependencies and virtual environments. The `pyproject.toml` 
file defines all of the dependencies, and `poetry.lock` resolves the dependency versions and locks
them so that we can install the exact same package versions every time.

You can think of poetry as a replacement for pip or conda, and the toml/lock files as replacements
for the requirements files.

We'll use poetry to install packages in the pyenv we installed/specified above.

```sh
pyenv shell 3.10.10
pip3 install poetry
pyenv shell --unset
```


## Direnv

We use direnv to automatically load the poetry virtual environment when you navigate to this project's
directory. THis helps so you don't have to activate/deactivate any environments yourself, and you
won't accidentally install packages in the wrong environment.

Direnv runs the `.envrc` file in this project.

### Install direnv

On mac:

```sh
brew install direnv
```

Then add this to your shell startup file (any platform):

```sh
eval "$(direnv hook $(basename $SHELL))
```

### Activating direnv

Run `direnv allow` anytime the `.envrc` file changes.

## Vscode

Vscode is not required, but I've set up some conveniences. You can launch the workspace by double
clicking the `.code-workspace` file to have some features set up for you.

Tips:
* Use the autoDocString extension with the google format enabled.
* Set the python environment by clicking on the right side of the blue bar at the bottom of the
window, and select the venv python (should be at `.venv/bin/python`)
* Make sure python & direnv are set correctly with the venv by typing `which python` in the terminal.

## Final setup

* Clone the repository.
* `cd` into the repository
* Execute `poetry config virtualenvs.in-project true` (tells poetry to install stuff in the `.venv` directory).
* Execute `poetry install`
