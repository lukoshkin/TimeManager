"""LLM Solutions configuration loader."""

from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from src.config.logging import logger


class RigidIntentConfig(BaseModel):
    """Configuration for rigid intent solution."""

    description: str
    features: list[str]
    limitations: list[str]


class LangChainReActModelConfig(BaseModel):
    """Model configuration for LangChain ReAct solution."""

    temperature: float = Field(default=0.1)
    max_tokens: int = Field(default=2000)


class LangChainReActMemoryConfig(BaseModel):
    """Memory configuration for LangChain ReAct solution."""

    enabled: bool = Field(default=True)
    type: str = Field(default="memory_saver")


class ModelConfig(BaseModel):
    """General model configuration."""

    provider: str = Field(
        default="openai",
        description="Model provider (openai, anthropic, etc.)",
    )
    name: str = Field(default="gpt-4o", description="Model name")
    temperature: float = Field(default=0.1, description="Model temperature")
    max_tokens: int = Field(default=2000, description="Maximum tokens")


class SemanticSearchConfig(BaseModel):
    """Semantic search configuration using Milvus."""

    enabled: bool = Field(default=True, description="Enable semantic search")
    collection_name: str = Field(
        default="calendar_events", description="Milvus collection name"
    )
    vector_dim: int = Field(default=384, description="Vector dimension")
    model_name: str = Field(
        default="text-embedding-3-small", description="Embedding model name"
    )
    model_provider: str = Field(
        default="openai", description="Embedding model provider"
    )


class LoggingConfig(BaseModel):
    """Logging configuration."""

    log_level: str = Field(
        default="DEBUG", description="General logging level"
    )
    litellm_log: str = Field(
        default="INFO", description="LiteLLM logging level"
    )
    app_log_level: str = Field(
        default="INFO", description="For custom log messages"
    )


class LangChainReActConfig(BaseModel):
    """Configuration for LangChain ReAct solution."""

    description: str
    features: list[str]
    memory: LangChainReActMemoryConfig


class LLMSolutionConfig(BaseModel):
    """LLM Solution selection configuration."""

    type: str = Field(description="Type of LLM solution to use")
    rigid_intent: RigidIntentConfig
    langchain_react: LangChainReActConfig


class DeploymentConfig(BaseModel):
    """Deployment configuration."""

    environment: str = Field(default="development")


class MCPServerFeatureConfig(BaseModel):
    """MCP Server feature configuration."""

    enabled: bool = Field(default=True)
    description: str = Field(
        default="Enable MCP server for external tool access"
    )


class SemanticSearchFeatureConfig(BaseModel):
    """Semantic search feature configuration."""

    enabled: bool = Field(default=True)
    description: str = Field(
        default="Enable Milvus semantic search for events"
    )


class DependenciesConfig(BaseModel):
    """Dependencies configuration by solution."""

    rigid_intent: list[str]
    langchain_react: list[str]


class LLMSolutionsConfig(BaseModel):
    """Main LLM Solutions configuration."""

    llm_solution: LLMSolutionConfig
    deployment: DeploymentConfig
    dependencies: DependenciesConfig
    model: ModelConfig = Field(
        default_factory=ModelConfig,
        description="Common model configuration",
    )
    semantic_search: SemanticSearchConfig = Field(
        default_factory=SemanticSearchConfig
    )
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    @classmethod
    def load_from_yaml(
        cls, config_path: str | Path | None = None
    ) -> "LLMSolutionsConfig":
        """Load configuration from YAML file.

        Args:
            config_path: Path to the config file. If None, uses default path.

        Returns
        -------
            Loaded configuration
        """
        config_path = Path(
            "llm_solutions_config.yaml" if config_path is None else config_path
        )
        if not config_path.exists():
            logger.warning(
                f"Config file {config_path} not found. Using defaults."
            )
            return cls._get_default_config()

        try:
            with open(config_path, encoding="utf-8") as file:
                yaml_data = yaml.safe_load(file)

            logger.info(f"Loaded LLM solutions config from {config_path}")
            return cls(**yaml_data)

        except Exception as exc:
            logger.error(f"Error loading config from {config_path}: {exc}")
            logger.warning("Using default configuration")
            return cls._get_default_config()

    @classmethod
    def _get_default_config(cls) -> "LLMSolutionsConfig":
        """Get default configuration.

        Returns
        -------
            Default configuration
        """
        return cls(
            model=ModelConfig(
                provider="openai",
                name="gpt-4o",
                temperature=0.1,
                max_tokens=2000,
            ),
            llm_solution=LLMSolutionConfig(
                type="langchain_react",
                rigid_intent=RigidIntentConfig(
                    description="Traditional intent-based parsing with predefined handlers",
                    features=[
                        "Fast response times",
                        "Deterministic behavior",
                        "Limited to predefined intents",
                    ],
                    limitations=[
                        "Cannot handle complex queries",
                        "No conversational context",
                        "Rigid structure",
                    ],
                ),
                langchain_react=LangChainReActConfig(
                    description="LangChain ReAct agent with calendar tools",
                    features=[
                        "Natural language understanding",
                        "Conversational context",
                        "Tool usage with reasoning",
                        "Flexible query handling",
                    ],
                    memory=LangChainReActMemoryConfig(
                        enabled=True, type="memory_saver"
                    ),
                ),
            ),
            deployment=DeploymentConfig(environment="development"),
            dependencies=DependenciesConfig(
                rigid_intent=[],
                langchain_react=[
                    "langchain",
                    "langchain-mcp-adapters",
                    "langchain-openai",
                    "langchain-core",
                    "langgraph",
                ],
            ),
        )

    def get_solution_type(self) -> str:
        """Get the selected LLM solution type.

        Returns
        -------
            Solution type ('rigid_intent' or 'langchain_react')
        """
        return self.llm_solution.type

    def get_required_dependencies(self) -> list[str]:
        """Get required dependencies for the selected solution.

        Returns
        -------
            List of required package names
        """
        solution_type = self.get_solution_type()
        if solution_type == "rigid_intent":
            return self.dependencies.rigid_intent
        elif solution_type == "langchain_react":
            return self.dependencies.langchain_react
        else:
            logger.warning(f"Unknown solution type: {solution_type}")
            return []


# Global instance for easy access
_config_instance: LLMSolutionsConfig | None = None


def get_llm_config() -> LLMSolutionsConfig:
    """Get the global LLM solutions configuration instance.

    Returns
    -------
        LLM solutions configuration
    """
    global _config_instance
    if _config_instance is None:
        _config_instance = LLMSolutionsConfig.load_from_yaml()
    return _config_instance


def reload_llm_config(
    config_path: str | Path | None = None,
) -> LLMSolutionsConfig:
    """Reload the LLM solutions configuration from file.

    Args:
        config_path: Path to the config file. If None, uses default path.

    Returns
    -------
        Reloaded configuration
    """
    global _config_instance
    _config_instance = LLMSolutionsConfig.load_from_yaml(config_path)
    return _config_instance
