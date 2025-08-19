#! /usr/bin/env python3

import requests
from dataclasses import dataclass
from colorama import Fore, Style
from datetime import datetime

COL_PKG_NAME = Fore.CYAN
COL_PKG_VER = Fore.BLUE
COL_PKG_VOTES = Fore.GREEN
COL_PKG_OUTDATED = Fore.RED

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

    for package in packages:
        print(f'{COL_PKG_NAME}{package.name}{Style.RESET_ALL} {COL_PKG_VER}{package.version}{Style.RESET_ALL} {COL_PKG_VOTES}[+{package.votes} ~{round(package.popularity, 2)}]{Style.RESET_ALL}', end='')

        if package.out_of_date is not None:
            dt = datetime.fromtimestamp(package.out_of_date)
            print(f' {COL_PKG_OUTDATED}OUT-OF-DATE {dt.strftime("%Y/%m/%d")}{Style.RESET_ALL}')
            # IMPROVE: actually parse when it was marked out of date, so that it can be compared to the current "system snapshot date"
        else:
            print()

        print(f'    {package.desc}')

if __name__ == '__main__':
    main()
