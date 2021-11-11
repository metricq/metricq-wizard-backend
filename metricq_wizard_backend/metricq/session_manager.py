# metricq-wizard
# Copyright (C) 2019 ZIH, Technische Universitaet Dresden, Federal Republic of Germany
#
# All rights reserved.
#
# This file is part of metricq-wizard.
#
# metricq-wizard is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# metricq-wizard is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with metricq-wizard.  If not, see <http://www.gnu.org/licenses/>.
from typing import Dict

from metricq import get_logger

from metricq_wizard_backend.metricq.user_session import UserSession

logger = get_logger()


class UserSessionManager:
    def __init__(self):
        self._user_sessions: Dict[str, UserSession] = {}

    def get_user_session(self, session_key) -> UserSession:
        session = self._user_sessions.get(session_key)

        if session is None:
            session = UserSession(session_key=session_key)
            self._user_sessions[session_key] = session

        return session
