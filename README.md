# pixelhasher-solo-helper

`pixelhasher-solo-helper` is a small server that pretends to be a zkBits pool for the
purpose of allowing [pixelhasher][1] to mine solo. Its job is to provide
`pixelhasher` with work to do, and to help `pixelhasher` submit solutions to
the blockchain.

If you have problems, please join the [zkBits Discord][2] and we'll help.

## Installation

Ubuntu 24.04 is recommended, but any similar system will work.

### Python

Your system probably already has Python, but it may not be the right version, and your system may not offer the version we want. What we need to do is to leave the system Python alone, but install a more modern version that's available to our mining user.

First, install dependencies Python needs. If you're on Ubuntu, run the following as root, or use `sudo`:
```
apt install -y build-essential libssl-dev zlib1g-dev libbz2-dev libreadline-dev libsqlite3-dev curl git libncursesw5-dev xz-utils tk-dev libxml2-dev libxmlsec1-dev libffi-dev liblzma-dev
```

If you're not on Ubuntu, [here's some information about how to get the dependencies for your system](https://github.com/pyenv/pyenv/wiki#suggested-build-environment).

Switch to the user you intend to use for mining, if different from root. This can be an ordinary user, because we're going to install the tools and Python into a home directory, not the system.

Install the installer called [mise](https://mise.jdx.dev/):
```
curl https://mise.run | sh
```

Add the following the bottom of your `~/.profile`:
```
export PATH=$HOME/.local/bin:$HOME/.local/share/mise/shims:$PATH
```

... and source it:
```
source ~/.profile
```

Finally, use `mise` to install a modern Python:
```
mise install python@3.12.4
mise use -g python@3.12.4
pip install pipenv
mise reshim
```

After that, things should look approximately like this:
```
$ which python
/home/dev/.local/share/mise/shims/python
$ python --version
Python 3.12.4
$ which pipenv
/home/dev/.local/share/mise/shims/pipenv
```

### Installing and running this project

Clone the repo:
```
git clone https://github.com/zkbits/pixelhasher-solo-helper.git
```

Install the dependencies:
```
cd pixelhasher-solo-helper
pipenv install
```

Configure options:

`cp conf.json.example conf.json` and edit `conf.json`.

The most important option is `privateKey`. Please use the private key of an
account you use only for mining, one that has minimal funds.

Configure `sprites.txt`. This file contains 64-byte pseudo-hex bitmap strings
that represent the images you want to mine.

`solo` is just going to extract bitmap strings from this file, so its format is
very free. You could put just the strings in the file like this:

```
000000000c3028143c3c3ffc3e7c1bd833cc37ec3e7c1e780c300e7000000000
000000002244200425a43c3c37ec07e002400e700ff00ff03ffc2c3400000000
```

... or you could do it like this, with comments for yourself:

```
000000000c3028143c3c3ffc3e7c1bd833cc37ec3e7c1e780c300e7000000000 koala deer
000000002244200425a43c3c37ec07e002400e700ff00ff03ffc2c3400000000 ghost robot
```

... or you could even do this:

```
000000000c3028143c3c3ffc3e7c1bd833cc37ec3e7c1e780c300e7000000000
................
................
....##....##....
..#.#......#.#..
..####....####..
..############..
..#####..#####..
...##.####.##...
..##..####..##..
..##.######.##..
..#####..#####..
...####..####...
....##....##....
....###..###....
................
................
000000002244200425a43c3c37ec07e002400e700ff00ff03ffc2c3400000000
................
................
..#...#..#...#..
..#..........#..
..#..#.##.#..#..
..####....####..
..##.######.##..
.....######.....
......#..#......
....###..###....
....########....
....########....
..############..
..#.##....##.#..
................
................
```

As `solo` successfully submits solutions, it will add sprites that it has done
to `sprites_done.txt`.

## Run

`make solo`

`solo` will do some basic sanity checks and then start listening on the
configured port for connections from `pixelhasher`.


[1]: https://github.com/zkbits/pixelhasher
[2]: https://discord.gg/T9kUShU4K3
