# How-to guides

(shell-cleanup)=
## Clean up your shell initialization logic

Since `conda-spawn` only relies on the `conda` entry point being on `PATH`, you will probably want to remove all the shell initialization stuff from your shell profiles with:

```bash
conda init --reverse
```

Then, make sure you have added `$CONDA_ROOT/condabin` to your PATH, with `$CONDA_ROOT` being the path to your conda installation. For example, assuming you installed `conda` in `~/conda`, your `~/.bashrc` would only need this line:

```bash
export PATH="${PATH}:${HOME}/conda/condabin"
```

On Windows, open the Start Menu and search for "environment variables". You will be able to add the equivalent location (e.g. `C:\Users\username\conda\condabin`) to the `PATH` variable via the UI.

(in-script)=
## Activate an environment inside a shell script

For in-script usage, please consider these replacements for `conda activate`:

For Unix shell scripts:

```bash
eval "$(conda spawn --hook --shell posix -n <ENV-NAME>)"
```

For Windows CMD scripts:

```batch
FOR /F "tokens=*" %%g IN ('conda spawn --hook --shell cmd -n <ENV-NAME>') do @CALL %%g
```

For Windows Powershell scripts:

```powershell
conda spawn --hook --shell powershell -n <ENV-NAME> | Out-String | Invoke-Expression
```

For example, if you want to create a new environment and activate it, it would look like this:

```bash
# Assumes `conda` is in PATH
conda create -n new-env python numpy
eval "$(conda spawn --hook --shell powershell -n new-env)"
python -c "import numpy"
```

## Nest activated environments

Nested activation is disallowed by default. Instead we strongly recommend to only activate one environment at a time. Either open a new terminal session (window, tab, `screen`, `tmux`...) or close the current one with `exit` or <kbd>Ctrl</kbd>+<kbd>D</kbd>, and then run `conda spawn` again.

That said, if you really want to reuse the current session, you can use one of these two nesting flags:

- `--replace` will deactivate the current environment and activate the new one. Only the binaries in the new environment will be visible in `PATH`.
- `--stack` will _not_ deactivate the current environment. Instead, it will activate the new one on top. Binaries in both environments will be visible in `PATH`, but the ones from the new environment will have precedence.
