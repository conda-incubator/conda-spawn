# conda-spawn

Activate conda environments in new shell processes.

> [!IMPORTANT]
> This project is still in early stages of development. Don't use it in production (yet).
> We do welcome feedback on what the expected behaviour should have been if something doesn't work!

## What is this?

`conda spawn` is a replacement subcommand for the `conda activate` and `conda deactivate` workflow

Instead of writing state to your current shell session, `conda spawn ENV-NAME` will start a new shell with your activated environment. To deactivate, exit the process with <kbd>Ctrl</kbd>+<kbd>D</kbd>, or run the command `exit`.

## Installation

This is a `conda` plugin and goes in the `base` environment:

```bash
conda install -n base conda-forge::conda-spawn
```

More information is available on our [documentation](https://conda-incubator.github.io/conda-spawn).

## Contributing

Please refer to [`CONTRIBUTING.md`](/CONTRIBUTING.md).
