"""Pluggable integration connectors (Sandbox + Live API adapters)."""

from backoffice_agent.connectors.accounting_connector import AccountingConnector
from backoffice_agent.connectors.crm_connector import CRMConnector
from backoffice_agent.connectors.email_connector import EmailConnector
from backoffice_agent.connectors.hris_connector import HRISConnector
from backoffice_agent.connectors.slack_connector import SlackConnector

__all__ = [
    "EmailConnector",
    "SlackConnector",
    "HRISConnector",
    "AccountingConnector",
    "CRMConnector",
]
