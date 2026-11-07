"""Public synchronous LangSmith clients for SmithDB-backed read operations."""


def create_reader(config):
    """Use the configured region and keep retries under the caller's control."""
    from langsmith import Langsmith

    return Langsmith(api_key=config['key'], base_url=config['endpoint'],
                     max_retries=0, timeout=2.0)


def resolve_project_id(config, reader, client):
    """Resolve an existing destination without creating a tracing project."""
    if config['destination'] == 'agent':
        return str(reader.sessions.resolve(**config['address']).session_id)
    return str(client.read_project(project_name=config['project']).id)
