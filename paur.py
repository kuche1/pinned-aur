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
COL_TARGET_DATE = Fore.LIGHTMAGENTA_EX

AUR_URL = 'https://aur.archlinux.org/rpc/'

MIRRORLIST_FILE = '/etc/pacman.d/mirrorlist'
MIRRORLIST_PREFIX = 'Server=https://archive.archlinux.org/repos/'

##########
########## class
##########

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

    @classmethod
    def from_aur_json_data(cls, data: dict) -> "Package":
        return cls(data['Name'], data['Description'], False, data['NumVotes'], data['Popularity'], data['Version'], data['OutOfDate'])

    @classmethod
    def from_pacman(cls, name: str, desc: str, version: str) -> "Package":
        # TODO: hacked votes
        return cls(name, desc, True, -1, float('inf'), version, None)

    @classmethod
    def from_pacman_foreign(cls, name: str, version: str) -> "Package | None":
        if name.endswith('-debug'):
            return None
        return cls.from_pacman(name, "UNKNOWN: foreign package", version)

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

    def install(self, mirrirlist_date: "MirrorlistDate") -> None:
        if self.source_is_pacman:
            # TODO: also include the repo (e.g. extra/name) ?
            subprocess.run(['sudo', 'pacman', '-S', '--', self.name], check=True)

        else:
            with tempfile.TemporaryDirectory() as tmpdir:
                cwd = tmpdir

                ##### clone

                subprocess.run(['git', 'clone', f'https://aur.archlinux.org/{self.name}.git'], check=True, cwd=cwd)
                cwd = f'{cwd}/{self.name}'

                ##### get latest commit

                latest_commit = subprocess.run(['git', 'rev-list', '-1', 'HEAD'], capture_output=True, check=True, cwd=cwd)
                latest_commit = latest_commit.stdout.strip()

                ##### get latest commit, before a certain date

                proc = subprocess.run(['git', 'rev-list', '-1', f'--before={mirrirlist_date.year}-{mirrirlist_date.month}-{mirrirlist_date.day} 23:59Z', 'HEAD'], capture_output=True, check=True, cwd=cwd)
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

@dataclass
class MirrorlistDate:
    year: int
    month: int
    day: int

    def __init__(self) -> None:
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

                # print(year, month, day)

                self.year = year
                self.month = month
                self.day = day
                return
                # TODO: and what if we have that same line more than 1 time ?

        raise NotImplementedError
        # TODO(vb): in this case, just act as if there is no date

##########
########## function
##########

#####
##### function: parse
#####

def parse_local_package():
    ... # TODO

#####
##### function: other
#####

def search_for_package_in_pacman(package_name: str) -> list[Package]:
    packages = []

    proc = subprocess.run(['pacman', '-Ss', '--', package_name], capture_output=True, check=False)
    if proc.returncode != 0:
        return packages

    lines = proc.stdout.decode().splitlines()

    for line_data, desc in zip(lines[0::2], lines[1::2], strict=True):
        i = line_data.index('/')
        _pacman_repo = line_data[:i]
        line_data = line_data[i+1:]

        i = line_data.index(' ')
        name = line_data[:i]
        line_data = line_data[i+1:]

        version = line_data
        if ' ' in version:
            version = version[:version.index(' ')]

        packages.append(Package.from_pacman(name, desc, version))

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
        packages.append(Package.from_aur_json_data(data))

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

def choose_package(packages: list[Package], mirrirlist_date: MirrorlistDate) -> Package | None:
    if len(packages) == 0:
        return None

    for package_num, package in reversed(list(enumerate(packages, start=1))):
        print(f'{COL_PKG_SELECTION}{package_num}{Style.RESET_ALL}/', end='')
        package.print()

    try:
        choice = input(f'{COL_TARGET_DATE}[{mirrirlist_date.year}/{mirrirlist_date.month}/{mirrirlist_date.day}]{Style.RESET_ALL} > ')
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

def search_and_install_package(package_to_search_for: str) -> None:
    packages = search_for_package(package_to_search_for)
    packages.sort(reverse=True, key=lambda pkg: (pkg.source_is_pacman, pkg.votes, pkg.popularity))

    mirrorlist_date = MirrorlistDate()

    package = choose_package(packages, mirrorlist_date)
    if package is None:
        print('No packages found')
        return

    package.install(mirrorlist_date)

def full_aur_upgrade() -> None:
    proc = subprocess.run(['pacman', '-Qm'], check=True, capture_output=True)
    # I assume that this returns 0 if there are 0 packages

    aur_packages = []

    for data in proc.stdout.decode().splitlines():
        package, version = data.split(' ')

        package = Package.from_pacman_foreign(package, version)
        if package is None:
            continue

        aur_packages.append(package)

    for package in aur_packages:
        print(f'{package=}')

    ... # TODO: implement

if __name__ == '__main__':
    # TODO: add the ability to update all packages
    # IMPROVE: give the user the ability to use the latest commit instead OR select a commit
    # TODO: add the ability to remove an aur package, alongside ALL it's dependencies
    # TODO: actually, do the dependencies even work ? maybe we should look for them, then install them with `--asdep`
    parser = argparse.ArgumentParser()
    parser.add_argument('package', type=str, nargs='?', help='Package to search for')
    parser.add_argument('--upgrade-aur', action='store_true')
    args = parser.parse_args()

    if args.upgrade_aur:
        if args.package is not None:
            print(f'ERROR: a specific package was specified during full AUR upgrade')
            sys.exit(1)
        full_aur_upgrade()
    else:
        search_and_install_package(args.package)
