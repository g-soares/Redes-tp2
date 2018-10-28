import sys
import socket
import threading
import select
import time
import json
import os
from struct import pack, unpack

TAM_MAX_PACOTE = 39+ (2**14)

class Rota():
	def __init__(self, destino, caminho, peso):
		self.destino = destino
		self.caminho = caminho
		self.peso = int(peso)
		self.timeStamp = time.time()

	def __str__(self):
		return f'''destino: {self.destino}
		\rcaminho: {self.caminho}
		\rpeso: {self.peso}
		\rtime stamp: {self.timeStamp}
		'''

class Router:
	def __init__(self):
		self.PORT = 55151
		self.mapa = {} #um dicionário que contém uma lista de rotas
		self.permissaoMapa = threading.Lock()
		self.ligado = True

	def setIp(self, host):
		self.HOST = host

	def setPeriod(self, period):
		self.period = int(period)

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
				self.adicionarDados(Rota(ip, ip, peso))
		except :
			print(f'Falha ao abrir o arquivo de startup-commands {nomeArquivo}')

	#adiciona dados ao vetor de distâncias
	def adicionarDados(self, rota):
		if rota.destino not in self.mapa:
			self.mapa[rota.destino] = []

		lista = self.mapa[rota.destino]

		with self.permissaoMapa:
			#testa lista vazia
			if not lista:
				#print('rota adicionada')
				lista.append(rota)
				self.iniciaTemporizador(rota.destino, rota.caminho)

			#testa se é uma rota alternativa ou a uma rota que já é conhecida
			elif lista[0].peso == rota.peso:
				existe = False

				for aux in lista:
					if aux.caminho == rota.caminho:
						#print('timeStamp atualizado')
						aux.timeStamp = rota.timeStamp
						existe = True

				if not existe :
					#print('rota alternativa')
					lista.append(rota)
					self.iniciaTemporizador(rota.destino, rota.caminho)

			#testa se é uma rota melhor
			elif lista[0].peso > rota.peso:
				#print('rota melhor')
				del lista[:]
				lista.append(rota)
				self.iniciaTemporizador(rota.destino, rota.caminho)

			#testa se a rota piorou
			elif (len(lista) == 1 and 
				lista[0].peso < rota.peso and 
				lista[0].caminho == rota.caminho):
				#print('rota pior')
				lista[0] = rota

			#testa se a rota piorou
			elif len(lista) > 1:
				#print('uma das rotas piorou')
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
			rotas = None

			with self.permissaoMapa:
				if destino in self.mapa:
					rotas = self.mapa[destino].copy()
			
			if rotas:
				for rota in rotas:
					if (rota.destino == destino and 
						rota.caminho == caminho and 
					   (time.time() - rota.timeStamp) < 4*self.period ):
						existeRota = True

				time.sleep(4*self.period)

		self.removerDados(destino, caminho)

	def removerDados(self, destino, caminho):
		if destino in self.mapa:
			with self.permissaoMapa:
				for count, rota in enumerate(self.mapa[destino]):
					if rota.caminho == caminho:
						del self.mapa[destino][count]
						break

			if not self.mapa[destino]:
				self.removerLink(destino)

	def removerLink(self, ip):
		with self.permissaoMapa:
			self.mapa.pop(ip)

	def enviarTrace(self, destino):
		pacote = {"type": "trace"}
		pacote["source"] = self.HOST
		pacote["destination"] = destino
		pacote["hops"] = []

		self.encaminharPacote(pacote)

	def encaminharPacote(self, pacote):
		#print(f'encaminhar pacote -> {pacote}')
		if pacote["type"] == "trace":
			pacote["hops"].append(f"{self.HOST}")

		pacoteEnviado = json.dumps(pacote)
		endereco = pacote["destination"]
		self.sock.sendto(pack('!{}s'.format(len(pacoteEnviado)),pacoteEnviado.encode())
			, (endereco, self.PORT))

		#altera a ordem da lista para fazer o balanceamento de carga
		if len(self.mapa[endereco]) > 1:
			with self.permissaoMapa:
				self.mapa[endereco] = self.mapa[endereco][1:].append(self.mapa[endereco][0])

	def tratarPacote(self, pacote):
		print(f'Tratar pacote -> {pacote}')
		if pacote["type"] == "data":
			print(pacote["payload"])

		elif pacote["type"] == "update":
			pesoAteVizinho = self.mapa[pacote["source"]][0].peso

			for dado in pacote["distances"]:
				self.adicionarDados(Rota(dado, pacote["source"], pacote["distances"][dado]+ pesoAteVizinho))
		
		elif pacote["type"] == "trace":
			pacote["hops"].append(self.HOST)
			novoPacote = {}
			novoPacote["type"] = "data"
			novoPacote["source"] = self.HOST
			novoPacote["destination"] = pacote["destination"]
			novoPacote["payload"] = pacote

			self.encaminharPacote(novoPacote)

	def rotearPacotes(self):
		while self.ligado:
			entrada = None
			entrada, saida, excecao = select.select([self.sock], [], [], 10)
			
			if entrada:
				dados, endereco = self.sock.recvfrom(TAM_MAX_PACOTE)
				pacote = json.loads(dados)
				
				if pacote["destination"] == self.HOST:
					self.tratarPacote(pacote)
				else:
					self.encaminharPacote(pacote)

	def rotearVetor(self):
		while self.ligado:
			time.sleep(self.period)
			dados = None

			print('---------------')
			print(self.mapa)
			print('---------------')

			with self.permissaoMapa:
				dados = self.mapa.copy()
			
			for endereco in dados:
				if dados[endereco][0].destino == dados[endereco][0].caminho:
					pacote = {"type": "update"}
					pacote["source"] = self.HOST
					pacote["destination"] = endereco
					distances = {}
					
					for auxEndereco in dados:
						#split horizon
						if not (dados[auxEndereco][0].caminho == endereco):
							distances[dados[auxEndereco][0].endereco] = dados[auxEndereco][0].peso

					distances[self.HOST] = 0
					pacote["distances"] = distances
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

		threadRoteandoPacotes = threading.Thread(target = roteador.rotearPacotes)
		threadRoteandoPacotes.start()

		threadRoteandoVetor = threading.Thread(target = roteador.rotearVetor)
		threadRoteandoVetor.start()

		while True:
			entrada = input().split(' ')
			if entrada[0] == 'add':
				roteador.adicionarDados(Rota(entrada[1],entrada[1],entrada[2]))
			elif entrada[0] == 'del':
				roteador.removerLink(entrada[1])
			elif entrada[0] == 'trace':
				roteador.enviarTrace(entrada[1])
			elif entrada [0] == 'quit':
				raise KeyboardInterrupt

	except KeyboardInterrupt:
		roteador.desligar()