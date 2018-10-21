import sys
import socket
import threading
import select
import time
import json
import os

TAM_MAX = 39+ (2**14)

class Rota():
	def __init__(self, destino, caminho, peso):
		self.destino = destino
		self.caminho = caminho
		self.peso = peso
		self.timeStamp = time.time()

class Router:
	def __init__(self):
		self.PORT = 55151
		self.mapa = {} #um dicionário que contém lista de listas 
		self.ligado = True
		self.permissaoMapa = threading.Lock()

	def setIp(self, host):
		self.HOST = host

	def setPeriod(self, period):
		self.period = period

	def desligar(self):
		self.ligado = False

	def bind(self):
		try :
			self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM,0)
			self.sock.bind((self.HOST, self.PORT))
		except socket.error:
			print ('Falha ao criar socket do servidor')
			sys.exit()

	def startupCommands(self, nomeArquivo):
		try:
			for linha in open(nomeArquivo,'r'):
				comando, ip, peso = linha.split(' ')
				if not (ip in self.mapa):
					self.mapa[ip] = []
				self.adicionarDados(Rota(ip, ip, peso))
		except :
			print(f'Falha ao abrir o arquivo de startup-commands {nomeArquivo}')

	
	#adiciona dados ao vetor de distâncias
	def adicionarDados(self, rota):
		lista = mapa[rota.destino]

		with permissaoMapa:
			if not lista: #testa lista vazia
				lista.appen(rota)
				self.iniciaTemporizador(rota.destino, rota.caminho)

			elif (lista[0].peso == rota.peso and 
				lista[0].caminho is not rota.caminho): #testa se é uma rota alternativa
				lista.append(rota)
				self.iniciaTemporizador(rota.destino, rota.caminho)

			elif lista[0].peso > rota.peso: #testa se é uma rota melhor
				del lista[:]
				lista.append(rota)
				self.iniciaTemporizador(rota.destino, rota.caminho)

			elif (len(lista) == 1 and 
				lista[0].peso < rota.peso and 
				lista[0].caminho == rota.caminho): #testa se a rota piorou
				lista[0] = rota

			elif len(lista) > 1: #testa se a rota piorou
				for count, dados in enumerate(lista):
					if dados.caminho == rota.caminho and dados.peso < rota.peso:
						del lista[count]
						break

	def iniciaTemporizador(self, destino, caminho):
		threadTemporizador = threading.Thread(target = self.supervisionarTempo, 
			args = [destino, caminho])
		threadTemporizador.start()

	def supervisionarTempo(self, destino, caminho):
		existeRota = True

		while existeRota:
			existeRota = False
			for rota in mapa[destino]:
				if (rota.destino == destino and 
					rota.caminho == caminho and 
				   (time.time() - rota.timeStamp) < 4*self.period ):
					existeRota = True

			time.sleep(4*self.period)

		self.removerDados(destino, caminho)

	def removerDados(self, destino, caminho):
		with permissaoMapa:
			for count, rota in enumerate(mapa[destino]):
				if rota.caminho == caminho:
					del mapa[destino][count]
					break

		if not mapa[destino]:
			self.removerLink(destino)

	def removerLink(self, ip):
		with permissaoMapa:
			mapa.pop(ip)

	def enviarTrace(self, destino):
		pass

	def encaminharPacote(self, pacote):
		pass

	def tratarPacote():
		pass

	def rotearPacotes(self):
		while self.ligado:
			entrada = None
			entrada, saida, excecao = select.select([self.sock], [], [], 10)
			
			if entrada:
				dados, endereco = self.sock.recvfrom(TAM_MAX)
				pacote = json.loads(dados)
				
				if pacote["destination"] == self.HOST:
					self.tratarPacote(pacote)
				else:
					self.encaminharPacote(pacote)

	def __str__(self):
		return f'''PORT: {self.PORT}
		\rHOST: {self.HOST}
		\rPeriodo: {self.period}
		'''

if __name__ == '__main__':
	roteador = Router()

	try :
		if len(sys.argv) < 3:
			print('Inicialização incorreta')
			sys.exit()
		elif len(sys.argv) < 4:
			roteador.setIp(sys.argv[1])
			roteador.setPeriod(sys.argv[2])
		elif len(sys.argv) < 5:
			roteador.setIp(sys.argv[1])
			roteador.setPeriod(sys.argv[2])
			roteador.startupCommands(sys.argv[3])
		else:
			for count, entrada in enumerate(sys.argv):
				if entrada == '--addr':
					roteador.setIp(sys.argv[count+1])
				elif entrada == '--update-period':
					roteador.setPeriod(sys.argv[count+1])
				elif entrada == '--startup-commands':
					roteador.startupCommands(sys.argv[count+1])

		roteador.bind()

		threadRoteando = threading.Thread(target = roteador.rotearPacotes)
		threadRoteando.start()

		while True:
			entrada = input().split(' ')
			if entrada[0] == 'add':
				roteador.adicionarDados(Rota(entrada[1],entrada[1],entrada[2]))
			elif entrada[0] == 'del':
				roteador.removerDados(Rota(entrada[1],entrada[1],entrada[2]))
			elif entrada[0] == 'trace':
				roteador.enviarTrace(entrada[1])
			elif entrada [0] == 'quit':
				raise KeyboardInterrupt

	except KeyboardInterrupt:
		roteador.desligar()