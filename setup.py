import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()


def get_requirements():
    with open("requirements.txt", "r") as reqs:
        requirements = reqs.read().splitlines()
    return requirements


setuptools.setup(
    name="pymusiclooper",
    version="1.5.1",
    author="arkrow",
    author_email="arkrow@protonmail.com",
    description="Automatically find loop points of any song and play endlessly or export into intro/loop/outro sections or loop points.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/arkrow/PyMusicLooper",
    install_requires=get_requirements(),
    extras_require={"complete": ["pytaglib>=1.4.6", "mpg123>=0.4"]},
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)",
        "Operating System :: OS Independent",
        "Topic :: Multimedia :: Sound/Audio",
    ],
    python_requires=">=3.6",
)
