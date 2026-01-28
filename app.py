from flask import Flask
from extensions import db
from blueprints.main import main_bp
from blueprints.admin import admin_bp
from blueprints.finance import finance_bp
import os

def create_app():
    app = Flask(__name__)
    
    # Configurações
    basedir = os.path.abspath(os.path.dirname(__file__))
    database_path = os.path.join(basedir, 'agenda.db')

    app.config['SECRET_KEY'] = 'agenda_controle_senha_hash24' 
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + database_path
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    db.init_app(app)

    # Registrar Blueprints
    app.register_blueprint(main_bp)
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(finance_bp, url_prefix='/finance')

    # --- NOVO FILTRO PARA LINKS EXTERNOS ---
    @app.template_filter('external_url')
    def external_url_filter(url):
        if not url: return ""
        # Remove espaços em branco acidentais
        url = url.strip()
        # Se já tiver protocolo, retorna igual
        if url.startswith('http://') or url.startswith('https://'):
            return url
        # Se não tiver, adiciona https://
        return 'https://' + url

    with app.app_context():
        db.create_all()

    return app

if __name__ == '__main__':
    app = create_app().run(debug=True, port=5000)