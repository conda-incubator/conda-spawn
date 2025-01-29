# Quickstart

## What is this?

`conda spawn` is a replacement subcommand for the `conda activate` and `conda deactivate` workflow.

Instead of writing state to your current shell session, `conda spawn ENV-NAME` starts a new shell with your activated environment. To deactivate, exit the process with <kbd>Ctrl</kbd>+<kbd>D</kbd>, or run the command `exit`.

The typical workflow looks like this:

```bash
~ $ which python
python not found
~ $ which conda
/Users/user/Miniforge/condabin/conda
~ $ conda spawn base
(base) ~ $ which python
/Users/user/Miniforge/bin/python
(base) ~ $ python my_project.py
working ...
ok!
(base) ~ $ export VAR=1
(base) ~ $ echo $VAR
1
(base) ~ $ exit
~ $ echo $VAR

~ $
```

As you can see, variables set during the `spawn`ed shell session do not leak in the parent session once closed with `exit`. If you have used `poetry shell` or `pixi shell`, this is essentially the same but for `conda`.

## Installation

This is a `conda` plugin and goes in the `base` environment:

```bash
conda install -n base conda-forge::conda-spawn
```

After this, you might want to {ref}`shell-cleanup`.

## Usage

To activate an environment named `my-project`:

```bash
conda spawn my-project
```

To deactivate, exit the process with <kbd>Ctrl</kbd>+<kbd>D</kbd>, or run the command `exit`.


## Why?

The main reasons include:

- Cleaner shell interaction with no need for a `conda` shell function.
- Avoid messing with existing shell processes.
- Faster shell startup when `conda` is not needed.
- Simpler installation and bookkeeping.

Do you want to learn more? Head over to {doc}`why`.
