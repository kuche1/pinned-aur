#! /usr/bin/env python3

import requests
from dataclasses import dataclass
from colorama import Fore, Style
from datetime import datetime
import sys
import tempfile
import subprocess
import argparse

COL_PKG_NAME = Fore.CYAN
COL_PKG_VER = Fore.BLUE
COL_PKG_VOTES = Fore.GREEN
COL_PKG_OUTDATED = Fore.RED
COL_PKG_SELECTION = Fore.MAGENTA
COL_PKG_INSTALLED = Fore.YELLOW

AUR_URL = 'https://aur.archlinux.org/rpc/'

MIRRORLIST_FILE = '/etc/pacman.d/mirrorlist'
MIRRORLIST_PREFIX = 'Server=https://archive.archlinux.org/repos/'

@dataclass
class Package:
    # there's more data in the json response,
    # I just don't see how it would be usefull

    name: str
    desc: str

    source_is_pacman: bool
    votes: int
    popularity: float

    version: str
    # maintainer: str
    out_of_date: None | int # int - unix timestamp

    def print(self) -> None:
        print(f'{COL_PKG_NAME}{self.name}{Style.RESET_ALL}', end='')

        installed = get_installed_package(self.name)
        if installed is not None:
            installed_name, installed_version = installed
            print(f' {COL_PKG_INSTALLED}[installed {installed_name} {installed_version}]{Style.RESET_ALL}', end='')

        print(f' {COL_PKG_VER}{self.version}{Style.RESET_ALL}', end='')

        print(f' {COL_PKG_VOTES}[', end='')
        if self.source_is_pacman:
            print(f'{COL_PKG_INSTALLED}pacman', end='')
        else:
            print(f'{self.votes} ~{round(self.popularity, 2)}', end='')
        print(f'{COL_PKG_VOTES}]{Style.RESET_ALL}', end='')

        if self.out_of_date is not None:
            dt = datetime.fromtimestamp(self.out_of_date)
            print(f' {COL_PKG_OUTDATED}[outdated {dt.strftime("%Y/%m/%d")}]{Style.RESET_ALL}', end='')
            # IMPROVE: compare to the current "system snapshot date"

        print()

        print(f'    {self.desc}')

    def install(self) -> None:
        if self.source_is_pacman:
            # TODO: also include the repo (e.g. extra/name) ?
            subprocess.run(['sudo', 'pacman', '-S', '--', self.name], check=True)

        else:
            target_year, target_month, target_day = get_mirrorlist_date()

            with tempfile.TemporaryDirectory() as tmpdir:
                cwd = tmpdir

                ##### clone

                subprocess.run(['git', 'clone', f'https://aur.archlinux.org/{self.name}.git'], check=True, cwd=cwd)
                cwd = f'{cwd}/{self.name}'

                ##### get latest commit

                latest_commit = subprocess.run(['git', 'rev-list', '-1', 'HEAD'], capture_output=True, check=True, cwd=cwd)
                latest_commit = latest_commit.stdout.strip()

                ##### get latest commit, before a certain date

                proc = subprocess.run(['git', 'rev-list', '-1', f'--before={target_year}-{target_month}-{target_day} 23:59Z', 'HEAD'], capture_output=True, check=True, cwd=cwd)
                # this `Z` is supposed to pin the timezone to UTC, rather than use the local time
                # TODO: actually go to a certain date, rather than to a hardcoded date

                if proc.stdout is None:
                    raise NotImplementedError
                    # TODO: let the user decide weather to use the latest commit OR to select a different commit

                relevant_commit = proc.stdout.strip()

                ##### reset to relevant commit

                proc = subprocess.run(['git', 'reset', '--hard', relevant_commit], check=True, cwd=cwd)

                ##### install

                subprocess.run(['makepkg', '-si'], check=True, cwd=cwd)

def search_for_package_in_pacman(package_name: str) -> list[Package]:
    packages = []

    proc = subprocess.run(['pacman', '-Ss', '--', package_name], capture_output=True, check=False)
    if proc.returncode != 0:
        return packages

    lines = proc.stdout.decode().splitlines()

    for line_data, desc in zip(lines[0::2], lines[1::2], strict=True):
        i = line_data.index('/')
        repo = line_data[:i]
        line_data = line_data[i+1:]

        i = line_data.index(' ')
        name = line_data[:i]
        line_data = line_data[i+1:]

        version = line_data
        if ' ' in version:
            version = version[:version.index(' ')]

        # TODO: hacked votes
        packages.append(Package(name, desc, True, -1, float('inf'), version, None))

    return packages

def search_for_package_in_aur(package_name: str) -> list[Package]:
    packages = []

    params = {
        'v': '5', # api version
        'type': 'search',
        'arg': package_name
    }

    response = requests.get(AUR_URL, params=params)
    response.raise_for_status()

    for data in response.json()['results']:
        # for example:
        # {'Description': 'Zoom VDI VMWare plugin', 'FirstSubmitted': 1706807860, 'ID': 1528188, 'LastModified': 1724630068, 'Maintainer': 'vachicorne', 'Name': 'zoom-vmware-plugin', 'NumVotes': 0, 'OutOfDate': None, 'PackageBase': 'zoom-vmware-plugin', 'PackageBaseID': 202104, 'Popularity': 0, 'URL': 'https://support.zoom.us/hc/en-us/articles/4415057249549-VDI-releases-and-downloads', 'URLPath': '/cgit/aur.git/snapshot/zoom-vmware-plugin.tar.gz', 'Version': '6.0.10-1'}
        package = Package(data['Name'], data['Description'], False, data['NumVotes'], data['Popularity'], data['Version'], data['OutOfDate'])
        packages.append(package)

    return packages

def search_for_package(package: str) -> list[Package]:
    packages = search_for_package_in_pacman(package)
    packages.extend(search_for_package_in_aur(package))
    return packages

def get_installed_package(name: str) -> None | tuple[str, str]:
    proc = subprocess.run(['pacman', '-Q', '--', name], check=False, capture_output=True)
    if proc.returncode != 0:
        return None
    name, version = proc.stdout.decode().strip().split(' ')
    return name, version

def get_mirrorlist_date() -> tuple[int, int, int]:
    with open(MIRRORLIST_FILE) as f:
        data = f.read().splitlines()

    for line in data:
        if line.startswith(MIRRORLIST_PREFIX):
            line = line[len(MIRRORLIST_PREFIX):]

            i = line.index('/')
            year = line[:i]
            line = line[i+1:]
            year = int(year)

            i = line.index('/')
            month = line[:i]
            line = line[i+1:]
            month = int(month)

            i = line.index('/')
            day = line[:i]
            line = line[i+1:]
            day = int(day)

            print(year, month, day)

            return year, month, day
            # TODO: and what if we have that same line more than 1 time ?

    raise NotImplementedError
    # TODO(vb): in this case, just act as if there is no date

def choose_package(packages: list[Package]) -> Package:
    for package_num, package in reversed(list(enumerate(packages, start=1))):
        print(f'{COL_PKG_SELECTION}{package_num}{Style.RESET_ALL}/', end='')
        package.print()

    try:
        choice = input('> ')
    except (KeyboardInterrupt, EOFError):
        sys.exit(0)

    try:
        choice = int(choice)
    except ValueError:
        print('ERROR: Not a number') # IMPROVE: color in red
        sys.exit(1)

    choice -= 1

    if (choice < 0) or (choice >= len(packages)):
        print('ERROR: Invalid choice') # IMPROVE: color in red
        sys.exit(1)

    return packages[choice]

def main(package_to_search_for: str) -> None:
    packages = search_for_package(package_to_search_for)
    packages.sort(reverse=True, key=lambda pkg: (pkg.source_is_pacman, pkg.votes, pkg.popularity))

    package = choose_package(packages)
    package.install()

if __name__ == '__main__':
    # TODO: add the ability to update all packages
    # TODO: add the ability to install regular `pacman` packages
    # IMPROVE: give the user the ability to use the latest commit instead OR select a commit
    # TODO: add the ability to remove an aur package, alongside ALL it's dependencies
    # TODO: actually, do the dependencies even work ? maybe we should look for them, then install them with `--asdep`
    parser = argparse.ArgumentParser()
    parser.add_argument('package', type=str, help='Package to search for')
    args = parser.parse_args()
    main(args.package)
