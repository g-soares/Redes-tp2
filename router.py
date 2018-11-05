import sys
import socket
import threading
import select
import time
import json
import os
from struct import pack

TAM_MAX_PACOTE = 39+(2**14)

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
		self.linkFixo = {} #um dicionário que contém as rotas adicionadas pelo usuário
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
				self.adicionarLinkFixo(Rota(ip, ip, peso))
		except :
			print(f'Falha ao abrir o arquivo de startup-commands {nomeArquivo}')

	def adicionarLinkFixo(self, rota):
		self.linkFixo[rota.destino] = rota
		self.adicionarDados(rota)

	#adiciona dados ao vetor de distâncias
	def adicionarDados(self, rota):
		if rota.destino not in self.mapa:
			self.mapa[rota.destino] = []

		listaDeRotas = self.mapa[rota.destino]

		with self.permissaoMapa:
			#testa lista vazia
			if not listaDeRotas:
				listaDeRotas.append(rota)
				self.iniciaTemporizador(rota.destino, rota.caminho)

			#testa se é uma rota alternativa ou a uma rota que já é conhecida
			elif listaDeRotas[0].peso == rota.peso:
				existe = False

				for aux in listaDeRotas:
					if aux.caminho == rota.caminho:
						aux.timeStamp = rota.timeStamp
						existe = True

				if not existe :
					listaDeRotas.append(rota)
					self.iniciaTemporizador(rota.destino, rota.caminho)

			#testa se é uma rota melhor
			elif listaDeRotas[0].peso > rota.peso:
				del listaDeRotas[:]
				listaDeRotas.append(rota)
				self.iniciaTemporizador(rota.destino, rota.caminho)

			#testa se a rota piorou
			elif (len(listaDeRotas) == 1 and 
				listaDeRotas[0].peso < rota.peso and 
				listaDeRotas[0].caminho == rota.caminho):
				listaDeRotas[0] = rota

			#testa se uma das rotas piorou
			elif len(listaDeRotas) > 1:
				for count, dados in enumerate(listaDeRotas):
					if dados.caminho == rota.caminho and dados.peso < rota.peso:
						del listaDeRotas[count]
						break

	def iniciaTemporizador(self, destino, caminho):
		threadTemporizador = threading.Thread(target = self.supervisionarTempo, 
			args = [destino, caminho])
		threadTemporizador.start()

	def supervisionarTempo(self, destino, caminho):
		existeRota = True
		tempoPercorrido = 0

		while existeRota and self.ligado:
			existeRota = False
			rotas = None

			with self.permissaoMapa:
				if destino in self.mapa:
					rotas = self.mapa[destino].copy()
			
			if rotas:
				for rota in rotas:
					atualizou = ((time.time() - rota.timeStamp) < 4*self.period and 
						rota.destino == destino and 
						rota.caminho == caminho)
					fixo = (destino in self.linkFixo and 
						self.linkFixo[destino].peso == rota.peso and 
						self.linkFixo[destino].caminho == caminho)
					
					if fixo or atualizou:
						if fixo:
							rota.timeStamp = time.time()
						
						existeRota = True
						tempoPercorrido = time.time() - rota.timeStamp

			if existeRota:
				time.sleep(4*self.period - tempoPercorrido)

		self.removerDados(destino, caminho)

	def removerDados(self, destino, caminho):
		with self.permissaoMapa:
			if destino in self.mapa:
				for count, rota in enumerate(self.mapa[destino]):
					if rota.caminho == caminho:
						del self.mapa[destino][count]
						break

		if destino in self.mapa and not self.mapa[destino]:
			self.removerLink(destino)

	def removerLink(self, ip):
		with self.permissaoMapa:
			if ip in self.mapa:
				self.mapa.pop(ip)

		if ip in self.linkFixo and self.ligado:
			self.adicionarDados(self.linkFixo[ip])

	def removerLinkFixo(self, ip):
		self.linkFixo.pop(ip)
		self.removerLink(ip)

	'''verifica se existe um caminho no mapa e 
	se o vizinho que informou sobre o caminho ainda está "vivo" '''
	def existeCaminho(self, ip, mapa):
		return (ip in mapa and mapa[ip] and mapa[ip][0].caminho in mapa and mapa[mapa[ip][0].caminho])

	def ehVizinho(self, rotas):
		resultado = False
		for rota in rotas:
			if rota.caminho == rota.destino:
				resultado = True

		return resultado

	def passaPeloVizinho(self, vizinho, rotas):
		resultado = False
		for rota in rotas:
			if rota.caminho == vizinho:
				resultado = True

		return resultado

	def enviarTrace(self, destino):
		pacote = {"type": "trace","source": self.HOST,"destination": destino, "hops": []}
		self.encaminharPacote(pacote)

	def encaminharPacote(self, pacote):
		if pacote["type"] == "trace":
			pacote["hops"].append(f"{self.HOST}")

		with self.permissaoMapa:
			#envia o pacote se o caminho existe no mapa
			if self.existeCaminho(pacote["destination"], self.mapa):
				endereco = self.mapa[pacote["destination"]][0].caminho
				pacoteEnviado = json.dumps(pacote)
				self.sock.sendto(pack(f'!{len(pacoteEnviado)}s', pacoteEnviado.encode())
					, (endereco, self.PORT))

			#altera a ordem da lista para fazer o balanceamento de carga
			if (pacote["destination"] in self.mapa and 
				len(self.mapa[pacote["destination"]]) > 1):
				self.mapa[pacote["destination"]] = self.mapa[pacote["destination"]][1:] + [self.mapa[pacote["destination"]][0]]

	def tratarPacote(self, pacote):
		if pacote["type"] == "data":
			print(pacote["payload"])

		elif pacote["type"] == "update":

			'''evita que um pacote de atualização seja processado antes do link 
			fixo ser adicionado e gere uma exceção por não se saber o custo até o vizinho'''
			if pacote["source"] in self.mapa and self.mapa[pacote["source"]]:
				pesoAteVizinho = self.mapa[pacote["source"]][0].peso
				for dado in pacote["distances"]:
					self.adicionarDados(Rota(dado, pacote["source"], pacote["distances"][dado]+ pesoAteVizinho))
		
		elif pacote["type"] == "trace":
			pacote["hops"].append(self.HOST)
			novoPacote = {"type": "data", "source": self.HOST, "destination": pacote["source"]}
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

			with self.permissaoMapa:
				dados = self.mapa.copy()

			for endereco in dados:
				if self.ehVizinho(dados[endereco]):
					pacote = {"type": "update", "source": self.HOST, "destination": endereco}
					distances = {}
					
					for auxEndereco in dados:
						if (self.existeCaminho(auxEndereco, dados) and 
							not self.passaPeloVizinho(endereco, dados[auxEndereco])):
							distances[auxEndereco] = dados[auxEndereco][0].peso

					distances[self.HOST] = 0
					pacote["distances"] = distances
					self.encaminharPacote(pacote)

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
				roteador.adicionarLinkFixo(Rota(entrada[1],entrada[1],entrada[2]))
			elif entrada[0] == 'del':
				roteador.removerLinkFixo(entrada[1])
			elif entrada[0] == 'trace':
				roteador.enviarTrace(entrada[1])
			elif entrada [0] == 'quit':
				raise KeyboardInterrupt

	except KeyboardInterrupt:
		roteador.desligar()