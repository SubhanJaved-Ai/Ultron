"""Tests for execution environment backends: Local, Docker, and SSH."""

from openjarvis.sandbox.environments import (
    DockerEnvironment,
    LocalEnvironment,
    SSHEnvironment,
    get_environment,
)


def test_local_environment_execution():
    env = LocalEnvironment()
    assert env.name == "local"
    assert env.is_available() is True

    res = env.execute("python -c \"print('Hello from local env')\"")
    assert res.success is True
    assert "Hello from local env" in res.stdout


def test_ssh_environment_args_construction():
    env = SSHEnvironment(
        host="my-cluster.ai",
        user="ubuntu",
        port=2222,
        key_path="~/.ssh/id_rsa",
        connect_timeout=5,
    )
    assert env.name == "ssh"

    args = env.build_ssh_args("nvidia-smi", cwd="/workspace")
    assert "-p" in args
    assert "2222" in args
    assert "ubuntu@my-cluster.ai" in args
    assert "cd /workspace && nvidia-smi" in args
    assert "-o" in args


def test_get_environment_factory():
    local_env = get_environment("local")
    assert isinstance(local_env, LocalEnvironment)

    ssh_env = get_environment("ssh", host="remote.host", user="root")
    assert isinstance(ssh_env, SSHEnvironment)
    assert ssh_env.host == "remote.host"
    assert ssh_env.user == "root"

    docker_env = get_environment("docker", container_id="test_container")
    assert isinstance(docker_env, DockerEnvironment)
    assert docker_env.container_id == "test_container"
