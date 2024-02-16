# concert_launcher
A minimal process launching automation tool based on YAML and TMUX

## Quickstart
Tailored to @alaurenzi 's laptop machine setup !

```bash
pip install -e .
cd config/example_alaurenzi  # a folder containing launcher.yaml
concert_launcher run cartesio  # run cartesio and its dependencies
concert_launcher mon  # spawn tmux monitoring session on local machine
concert_launcher status  # print process tree
concert_launcher kill [proc_name]  # kill proc_name (or all)
```
