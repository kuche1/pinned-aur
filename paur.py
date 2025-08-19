#! /usr/bin/env python3

import requests
from dataclasses import dataclass
from colorama import Fore, Style
from datetime import datetime
import sys

COL_PKG_NAME = Fore.CYAN
COL_PKG_VER = Fore.BLUE
COL_PKG_VOTES = Fore.GREEN
COL_PKG_OUTDATED = Fore.RED
COL_PKG_SELECTION = Fore.MAGENTA

URL = 'https://aur.archlinux.org/rpc/'

@dataclass
class Package:
    # there's more data in the json response,
    # I just don't see how it would be usefull

    name: str
    desc: str

    votes: int
    popularity: float

    version: str
    # maintainer: str
    out_of_date: None | int # int - unix timestamp


def search_package(name: str) -> list[Package]:
    params = {
        'v': '5', # api version
        'type': 'search',
        'arg': 'vmware'
    }

    response = requests.get(URL, params=params)

    response.raise_for_status() # IMPROVE: idk what this function is

    packages = []

    for data in response.json()['results']:
        # for example:
        # {'Description': 'Zoom VDI VMWare plugin', 'FirstSubmitted': 1706807860, 'ID': 1528188, 'LastModified': 1724630068, 'Maintainer': 'vachicorne', 'Name': 'zoom-vmware-plugin', 'NumVotes': 0, 'OutOfDate': None, 'PackageBase': 'zoom-vmware-plugin', 'PackageBaseID': 202104, 'Popularity': 0, 'URL': 'https://support.zoom.us/hc/en-us/articles/4415057249549-VDI-releases-and-downloads', 'URLPath': '/cgit/aur.git/snapshot/zoom-vmware-plugin.tar.gz', 'Version': '6.0.10-1'}
        package = Package(data['Name'], data['Description'], data['NumVotes'], data['Popularity'], data['Version'], data['OutOfDate'])
        packages.append(package)

    return packages

def main() -> None:
    packages = search_package('vmware')
    packages.sort(key=lambda pkg: (pkg.votes, pkg.popularity))

    for package_idx, package in reversed(list(enumerate(packages))):
        print(f'{COL_PKG_SELECTION}{package_idx}{Style.RESET_ALL}/{COL_PKG_NAME}{package.name}{Style.RESET_ALL} {COL_PKG_VER}{package.version}{Style.RESET_ALL} {COL_PKG_VOTES}[+{package.votes} ~{round(package.popularity, 2)}]{Style.RESET_ALL}', end='')

        if package.out_of_date is not None:
            dt = datetime.fromtimestamp(package.out_of_date)
            print(f' {COL_PKG_OUTDATED}OUT-OF-DATE {dt.strftime("%Y/%m/%d")}{Style.RESET_ALL}')
            # IMPROVE: compare to the current "system snapshot date"
        else:
            print()

        print(f'    {package.desc}')

    choice = input('> ')

    try:
        choice = int(choice)
    except ValueError:
        print('ERROR: Not a number') # IMPROVE: color in red
        sys.exit(1)

    if (choice < 0) or (choice >= len(packages)):
        print('ERROR: Invalid choice') # IMPROVE: color in red
        sys.exit(1)

    package = packages[choice]

    # TODO
    # git clone https://aur.archlinux.org/vmware-workstation.git
    # cd vmware-workstation
    # git log
    # git reset --hard COMMIT
    # makepkg -si

if __name__ == '__main__':
    # TODO: add the ability to actually install
    # TODO: go back to commit X, and only then install
    # TODO: add the ability to update all packages
    # TODO: add the ability to install regular `pacman` packages
    # IMPROVE: give the user the ability to use the latest commit instead OR select a commit
    main()
