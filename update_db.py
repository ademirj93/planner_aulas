import os
import shutil
from datetime import datetime
from sqlalchemy import inspect, text
from extensions import db

def update_database(app=None):
    print("Iniciando rotina de verificação do Banco de Dados...")
    
    # 1. Carrega a aplicação
    # Nota: O `create_app()` nativamente chama `db.create_all()`, 
    # o que por si só já garante que novas TABELAS sejam criadas caso não existam.
    if app is None:
        from app import create_app
        app = create_app()
        
    db_path = app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '')
    
    with app.app_context():
        inspector = inspect(db.engine)
        existing_tables = inspector.get_table_names()
        metadata_tables = db.metadata.tables
        
        # Lista para guardar as alterações necessárias
        alter_queries = []
        
        # 2. Compara colunas das tabelas nos models com o banco atual
        for table_name, table in metadata_tables.items():
            if table_name in existing_tables:
                # Pega nomes das colunas reais que estão no banco de dados SQLite
                existing_columns = {c['name'] for c in inspector.get_columns(table_name)}
                
                for column in table.columns:
                    if column.name not in existing_columns:
                        # Monta o tipo SQL da nova coluna
                        col_type = column.type.compile(db.engine.dialect)
                        
                        # Tratamento de valor padrão (SQLite exige DEFAULT para adicionar NOT NULL com dados)
                        default_clause = ""
                        if column.server_default:
                            default_clause = f" DEFAULT {column.server_default.arg}"
                        elif column.default is not None and getattr(column.default, 'arg', None) is not None:
                            arg = column.default.arg
                            if isinstance(arg, (int, float, str, bool)):
                                val = 1 if arg is True else (0 if arg is False else arg)
                                if isinstance(val, str):
                                    val = f"'{val}'"
                                default_clause = f" DEFAULT {val}"
                        
                        # Fallback de segurança para colunas NOT NULL sem default explícito
                        if not column.nullable and not default_clause:
                            col_type_str = str(col_type).upper()
                            if 'VARCHAR' in col_type_str or 'TEXT' in col_type_str or 'STRING' in col_type_str:
                                default_clause = " DEFAULT ''"
                            elif 'INT' in col_type_str or 'FLOAT' in col_type_str or 'NUMERIC' in col_type_str:
                                default_clause = " DEFAULT 0"
                            elif 'BOOLEAN' in col_type_str:
                                default_clause = " DEFAULT 0"
                        
                        stmt = f"ALTER TABLE {table_name} ADD COLUMN {column.name} {col_type}{default_clause};"
                        alter_queries.append((table_name, column.name, stmt))
        
        # 3. Se houver colunas para adicionar, faz o backup e atualiza o esquema
        if alter_queries:
            print(f"Foram encontradas {len(alter_queries)} coluna(s) ausente(s).")
            
            # Backup de segurança
            if os.path.exists(db_path):
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_path = f"{db_path}.{timestamp}.bak"
                shutil.copy2(db_path, backup_path)
                print(f"[Backup] Cópia de segurança criada em: {backup_path}")
            
            # Aplica as novas colunas
            with db.engine.connect() as conn:
                for table_name, col_name, stmt in alter_queries:
                    try:
                        print(f" -> Adicionando coluna '{col_name}' na tabela '{table_name}'...")
                        conn.execute(text(stmt))
                    except Exception as e:
                        print(f"[Erro] Falha ao alterar a tabela {table_name}: {e}")
                conn.commit()
            print("\nAtualização de estrutura concluída com sucesso!")
        else:
            print("\nO banco de dados já está totalmente atualizado com suas tabelas e colunas.")

if __name__ == "__main__":
    update_database()