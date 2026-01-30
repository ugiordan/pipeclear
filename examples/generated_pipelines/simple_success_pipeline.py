from kfp import dsl
from kfp.dsl import Input, Output, Dataset, Model

@dsl.component(
    base_image="quay.io/modh/runtime-images:ubi9-python-3.11",
    packages_to_install=['pandas', 'sklearn']
)
def notebook_component():
    """Auto-generated component from notebook cells."""
    import pandas as pd
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import train_test_split
    # Load data
    df = pd.read_csv('data.csv')
    X = df.drop('target', axis=1)
    y = df['target']
    # Train model
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2)
    model = RandomForestClassifier()
    model.fit(X_train, y_train)
    print(f'Accuracy: {model.score(X_test, y_test)}')


@dsl.pipeline(
    name="1_simple_success",
    description="Auto-generated from notebook"
)
def 1_simple_success():
    """Pipeline generated from Jupyter notebook."""
    task = notebook_component()


if __name__ == '__main__':
    from kfp import compiler
    compiler.Compiler().compile(
        pipeline_func=1_simple_success,
        package_path='1_simple_success.yaml'
    )
