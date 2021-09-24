# metricq-wizard-plugin-http
# Copyright (C) 2019 ZIH, Technische Universitaet Dresden, Federal Republic of Germany
#
# All rights reserved.
#
# This file is part of metricq-wizard-plugin-http.
#
# metricq-wizard-plugin-http is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# any later version.
#
# metricq-wizard-plugin-http is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with metricq-wizard-plugin-http.  If not, see <http://www.gnu.org/licenses/>.
from setuptools import setup

setup(
    name="metricq_wizard_plugin_source_lmgd",
    version="0.1",
    author="TU Dresden",
    python_requires=">=3.8",
    packages=["metricq_wizard_plugin_source_lmgd"],
    scripts=[],
    install_requires=["metricq-wizard-backend"],
)
