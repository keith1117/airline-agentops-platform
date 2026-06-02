from .config import settings
from .rag import PolicyRAG


def main() -> None:
    rag = PolicyRAG(settings.rag_policy_path)
    cache = rag._load_or_build_embedding_cache()
    print(
        "Built policy embedding index: "
        f"chunks={len(cache.get('chunks', []))}, "
        f"model={cache.get('embedding_model')}, "
        f"dimensions={cache.get('embedding_dimensions')}, "
        f"path={settings.rag_embedding_cache}"
    )


if __name__ == "__main__":
    main()
