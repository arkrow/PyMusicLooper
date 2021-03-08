import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()


def get_requirements():
    with open("requirements.txt", "r") as reqs:
        requirements = reqs.read().splitlines()
    return requirements


setuptools.setup(
    name="pymusiclooper",
    version="2.2.0",
    author="arkrow",
    author_email="arkrow@protonmail.com",
    description="Automatically find the loop points of any music file and export into intro/loop/outro sections or loop points, with optional playback through the terminal.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/arkrow/PyMusicLooper",
    entry_points={
        "console_scripts": ["pymusiclooper=pymusiclooper.__main__:cli_main"],
    },
    install_requires=get_requirements(),
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)",
        "Operating System :: OS Independent",
        "Topic :: Multimedia :: Sound/Audio",
    ],
    python_requires=">=3.6",
)
