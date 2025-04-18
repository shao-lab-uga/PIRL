import numpy as np
import pandas as pd
import scipy.io
import os
import random
import torch
import h5py

ENABLE_DEBUG = True

class SimpleSpeed():
    def __init__(self, dataPath, SELECT_PREC_ID=None, SELECT_OBSERVATION='state', options={}):

        self.Debug = {} # debug variable dict
        # vehicle parameters
        m = 2000
        g = 9.81
        mu = 0.01
        theta_0 = 0
        C_wind = 0.3606
        # min p1 v + p2 v^3 + p3 v a
        p1 = mu*m*g*np.cos(theta_0) + m*g*np.sin(theta_0)
        p2 = C_wind
        p3 = m
        self.Veh = {'m': m,
                    'g': g,
                    'mu': mu,
                    'theta_0': theta_0,
                    'C_wind': C_wind,
                    'p1': p1,
                    'p2': p2,
                    'p3': p3}

        # create a dummy preceding vehicle speed
        self.dt = 0.1
            
        # objective function weights
        self.w1 = 1e-4
        # self.w1 = 1
        self.w2 = 1
        self.w3 = 0
        # constraints
        self.dmax = 50
        self.dmin = 10
        self.dstop = 1
        self.hlb = 0.5
        self.vmax = 25
        self.vmin = 0
        self.amax = 3
        self.amin = -3
        self.dlbFunc = lambda v: self.dstop + self.hlb*v
        self.dataPath = dataPath
        self.SELECT_OBSERVATION = SELECT_OBSERVATION
        if 'EnableOldFashion' in options.keys():
            self.OLD_FASHION = options['EnableOldFashion']
        else:
            self.OLD_FASHION = False
        self.reset(options=options)



    def __GetLagrangeCoeff(self, n, x, y):
        L = [1]*(n+1)
        Lbasis = [1]*(n+1)

        # try to get combined coefficients
        for k in range(0, n+1): # start the outer loop through the data values for x
            
            for kk in range(0, (k)): # start the inner loop through the data values for x (if k = 0 this loop is not executed)
                L[k] = np.polymul(L[k],[1/(x[k]-x[kk]), - x[kk]/(x[k]-x[kk])]) # see the Lagrange interpolating polynomials
            
            for kk in range(k+1, n+1): # start the inner loop through the data values (if k = n this loop is not executed)
                L[k] = np.polymul(L[k],[1/(x[k]-x[kk]), - x[kk]/(x[k]-x[kk])]) # see the Lagrange interpolating polynomials

            pass
            Lbasis[k] = L[k]
            L[k] = y[k]*L[k]

        L = np.sum(np.array(L), axis=0)
        return L, Lbasis

    #def updatePrecedingVehicle(self, SELECT_PREC_ID=None, DATA_FILTER=None, IS_INIT=False, T_BEG=None, T_HORIZON=None, INIT_STATE=None):
    def updatePrecedingVehicle(self, options={}):
        # parser options
        if 'EnableRandomVehicle' in options.keys():
            if not options['EnableRandomVehicle'] and not self.IS_INIT:
                return
        if 'selectPrecedingId' in options.keys():
            SELECT_PREC_ID = options['selectPrecedingId']
        else:
            SELECT_PREC_ID = None
        if 'dataFilter' in options.keys():
            DataFilterFunc = options['dataFilter']
        else:
            DataFilterFunc = None
        if 'tBeg' in options.keys():
            T_BEG = options['tBeg']
        else:
            T_BEG = None
        if 'tHorizon' in options.keys():
            T_HORIZON = options['tHorizon']
        else:
            T_HORIZON = None
        if 'InitialState' in options.keys():
            INIT_STATE = options['InitialState']
        else:
            INIT_STATE = None       

        if 'manualPrecedingVehicleData' in options.keys(): 
            PrecInfo = options['manualPrecedingVehicleData']
        else:
            PrecInfo = None

        ControlMode = {'StopLine': False, 
                       'Terminate': False}

        if SELECT_PREC_ID is None:
            RAND_VEH = True
        else:
            RAND_VEH = False

        if self.IS_INIT:
            if self.OLD_FASHION:
                self.TrafficData = scipy.io.loadmat(self.dataPath)
                # remove not needed keys
                del self.TrafficData['__header__']
                del self.TrafficData['__version__']
                del self.TrafficData['__globals__']
                self.vehNames = sorted(self.TrafficData)
            else:
                # print(self.dataPath)
                self.TrafficData = h5py.File(self.dataPath, 'r')
                self.vehNames = np.array(sorted(self.TrafficData))[1:]

            # randomdize vehicle
            # if speed is almost all zero, we want to skip it to next time or speed
            vpSum = 0
            vpAvrg = 0
            it = 0
            NOT_VALID = True
            while NOT_VALID: #vpAvrg < 2:

                if PrecInfo is not None:
                    time = PrecInfo['t']
                    distance = PrecInfo['d']
                    speed = PrecInfo['v']
                    vehId = PrecInfo['id']
                elif self.OLD_FASHION:
                    if RAND_VEH:
                        vehId = random.sample(self.vehNames, 1)[0] #round(np.random.uniform(3,self.nVehicle))
                        SELECT_PREC_ID = int(vehId[4:])
                    else:
                        vehId = 'veh_{}'.format(SELECT_PREC_ID)

                    time = self.TrafficData[vehId][0][0][0][0]
                    distance = self.TrafficData[vehId][0][0][3][0]
                    speed = self.TrafficData[vehId][0][0][4][0]
                else:
                    # we do a find every time Env.reset(), this is still ok for tens of thousands of data
                    if RAND_VEH:
                        if DataFilterFunc is None:
                            vehId = np.random.choice(self.vehNames)
                        else:

                            # now we assume this datafilter is a function 
                            if self.IS_INIT:
                                self.VehNamesFiltered = DataFilterFunc(self.vehNames) # get the vehicle sthat satisfy filter condition
                            # then random select from the candidates
                            vehId = np.random.choice(self.VehNamesFiltered)
                        SELECT_PREC_ID = int(vehId.split('_')[1])
                    else:
                        vehId = SELECT_PREC_ID

                    time = np.array(self.TrafficData[vehId]['time']).reshape(-1)
                    distance = np.array(self.TrafficData[vehId]['distance']).reshape(-1)
                    speed = np.array(self.TrafficData[vehId]['speed']).reshape(-1)

                # randomdize time
                if T_HORIZON is None:
                    tHorizon = 10
                else:
                    tHorizon = T_HORIZON

                # normalize time first
                if T_BEG is None:
                    tBegSel = round(np.random.uniform(time[0], time[-1]-tHorizon))
                else:
                    #tBegSel = time[0]+2 # time[0]+14
                    tBegSel = time[0]+T_BEG
                tBeg = np.minimum(np.maximum(tBegSel, time[0]), time[-1]-tHorizon)
                tEnd = tBeg+tHorizon 
                idx = np.where((time >= tBeg - 1e-7) & (time <= tEnd + 1e-7))[0]

                # its possible the cycle is too short,
                # OR vehicle change lane and come back, if so, skip
                if len(idx) != int(tHorizon/self.dt+1):
                    continue

                tBegIdx = idx[0]

                t = time[idx]-time[idx[0]]+0.1 # add 0.1 so that initial polynomial states are non-zero
                dp = distance[idx]-distance[idx[0]]+0.1 
                vp = speed[idx]
                ap = np.hstack((np.diff(vp),np.array([0])))/self.dt
                
                # if speed is almost all zero, we want to skip it to next time or speed
                vpSum = np.sum(vp)
                vpAvrg = np.average(vp)

                it = it+1

                NOT_VALID = vpAvrg < 2
                # if preceding vehicle is all zero speed, we need different control
                if NOT_VALID and (T_BEG is not None):
                    ControlMode['StopLine'] = True
                    break

            # divide into intervals of 5 seconds
            tIntDur = 5 # second
            tIntBeg = np.arange(t[0],t[-1]-1,tIntDur)
            tIntEnd = np.arange(t[0]+tIntDur,t[-1]+1,tIntDur)  

            #  get all the tau points
            n = 3 # polynomial of order 5, for LGL need to minus 1
            #tauList = legendre_gauss_lobatto_nodes(n)
            tauList = np.array([-1.0, -0.4472135954999579, 0.4472135954999579, 1.0])

            fArr = [np.nan]*len(tIntBeg)
            fBasis = [np.nan]*(len(tIntBeg))
            dpBasis = [np.nan]*(len(tIntBeg))
            for i, _ in enumerate(tIntBeg):
                tList = ((1-tauList)*tIntBeg[i] + (1+tauList)*tIntEnd[i])/2
                dpVal = np.interp(tList, t, dp)

                L, Lbasis = self.__GetLagrangeCoeff(n,tList,dpVal)

                fArr[i] = np.flip(L)
                fBasis[i] = np.array(Lbasis)
                dpBasis[i] = dpVal

            self.fArr = fArr # coefficients of lower order first, higher order last [p0,p1,p2,p3] -> p3*t^3+p2*t^2+p1*t+p0
            self.fBasis = fBasis
            self.dpBasis = dpBasis

            self.nPoly = n
            self.nIntvl = len(tIntBeg)
            self.nIntvlIdx = round(tIntDur/self.dt)

            self.dmax = 80
            self.dmin = 10

            if INIT_STATE is None:
                dfollow0 = np.random.uniform(self.dmin+5, self.dmax-5)
                # initial conditions
                d0 = dp[0]-dfollow0
                v0 = min(max(np.random.uniform(vp[0]-5, vp[0]+5), 0), self.vmax)
            else:
                d0=INIT_STATE['d0']
                v0=INIT_STATE['v0']
                #a0=INIT_STATE['a0']
            # terminal conditions
            df = dp[-1]-30 #dp[-1]-dfollow0
            vf = vp[-1]
            af = 0
        else:
            pass
        self.SELECT_PREC_ID = SELECT_PREC_ID
        self.vehId = vehId
        
        N = len(t)-1
        self.N = N

        self.t = t

        self.dp = dp
        self.vp = vp
        self.ap = ap

        self.d0 = d0
        self.v0 = v0
        #self.a0 = a0
        self.df = df
        self.vf = vf
        self.af = af

        self.tBeg = tBeg
        self.tBegIdx = tBegIdx

        if tEnd >= time[-1]-self.dt:
            ControlMode['Terminate'] = True

        Info = {
                'fArr': fArr,
                'fBasis': fBasis,
                'dpBasis': dpBasis,
                }
        
        self.ControlMode = ControlMode
        return ControlMode, Info

    def reset(self, options={}):
        _,_ = self.updatePrecedingVehicle(options=options)

        # internal state to track the current position and speed of this vehicle
        self.state = torch.FloatTensor([self.d0, self.v0])
        self.nState = len(self.state)
        self.info = {}
        self.k = 0
        
        self.smin = np.array([self.dp[0]-self.dmax-1, self.vmin])
        self.smax = np.array([self.dp[-1]-self.dmin+1, self.vmax])

        self.nState = len(self.state)

        #self.observation, self.nObservation = self.resetObservation()
        self.observation = self.state2Observation(self.state)[0,:]
        self.nObservation = len(self.observation)

        self.nAction = 1
        
        if self.SELECT_OBSERVATION == 'exp':
            # df, v, k
            self.xmean = torch.FloatTensor([50., 5., 50.])
            self.xstd = torch.FloatTensor([10., 5., 30])   
            self.obsmin = torch.FloatTensor([0., 0., 0.])
            self.obsmax = torch.FloatTensor([self.dmax+5, self.vmax+1., self.N+2])
            
        elif self.SELECT_OBSERVATION == 'poly':
            self.xmean = torch.FloatTensor([50., 5., 50., -1, 1, 40, 40, 4, -14, 122, 122, -9, 17, 171, 176])
            self.xstd = torch.FloatTensor([10., 5., 30., 25, 32, 25, 25, 30, 75, 65, 52, 148, 434, 421, 297])
            self.obsmin = torch.FloatTensor([0., 0., 0., -1e5, -1e5, -1e5, -1e5, -1e5, -1e5, -1e5, -1e5, -1e5, -1e5, -1e5, -1e5])
            self.obsmax = torch.FloatTensor([self.dmax+5, self.vmax+1., self.N+2, 1e5, 1e5, 1e5, 1e5, 1e5, 1e5, 1e5, 1e5, 1e5, 1e5, 1e5, 1e5])
        
        self.umean = torch.FloatTensor([0])
        self.ustd = torch.FloatTensor([1])

        return self.observation

    def getNextState(self, state, action):
        # make sure np array is N-by-1
        state = state.reshape(-1,self.nState)
        action = action.reshape(-1,1)

        # np array input
        d = state[:,0]
        v = state[:,1]
        a = action[:,0]

        if state.shape[0] != action.shape[0]:
            stateNext = torch.empty((action.shape[0], state.shape[1]))
        else:
            stateNext = torch.empty(state.shape)

        # move forward one step to get next state
        stateNext[:,0] = d + self.dt*v
        stateNext[:,1] = torch.minimum(torch.maximum(v + self.dt*a, torch.tensor(self.vmin)), torch.tensor(self.vmax))
        return stateNext
    

    def state2Observation(self, state, k=None, vehId=None, tBeg=None):

        # make sure np array is N-by-1
        if not torch.is_tensor(state):
            state = torch.FloatTensor(state)
        state = state.reshape(-1,self.nState)

        # handle different k input
        if k is None:
            k = self.k
        if not torch.is_tensor(k):
            k = k*torch.ones(state.shape[0]).int()

        if state.shape[0] != k.shape[0]:
            k = k[0]*torch.ones(state.shape[0]).int()
        if vehId is not None:
            if state.shape[0] != vehId.shape[0]:
                vehId = vehId[0]*torch.ones(state.shape[0]).int()
            if state.shape[0] != tBeg.shape[0]:
                tBeg = tBeg[0]*torch.ones(state.shape[0]).int()

        #dpt, vpt = self.getPrecedingVehicle(k, vehId, tBeg)
        kClip = torch.minimum(k, torch.FloatTensor([self.N])).int()
        dpt = torch.FloatTensor(self.dp)[kClip]
        vpt = torch.FloatTensor(self.vp)[kClip]
        if self.SELECT_OBSERVATION == 'exp':
            observation = torch.column_stack((dpt-state[:,0],
                                state[:,1],
                                k))
        elif self.SELECT_OBSERVATION == 'test':
            observation = torch.column_stack((dpt-state[:,0],
                                state[:,1],
                                k,
                                vpt-state[:,1]))
        elif self.SELECT_OBSERVATION == 'poly':
            idx = torch.minimum(torch.floor(k/self.nIntvlIdx),torch.tensor(self.nIntvl-1)).int()
            
            dpNext = torch.matmul(torch.FloatTensor([[np.power(self.dt,3), np.power(self.dt,2), np.power(self.dt,1), 1]]), \
                                        torch.transpose(torch.FloatTensor(self.fArr)[idx],0,-1)*torch.row_stack([(k+1)**3, (k+1)**2, k+1, torch.ones(k.shape)]))

            observation = torch.empty(state.shape[0],3+self.nIntvl*(self.nPoly+1))
            observation[:,0] = dpNext-state[:,0]
            observation[:,1] = state[:,1]
            observation[:,2] = k
            
            # observation poly, from highest order to zero order
            # fArr [p0,p1,p2,p3] -> p3*t^3+p2*t^2+p1*t+p0
            for i in range(self.nIntvl):
                for j in range(self.nPoly):
                    observation[:,3+i*(self.nPoly+1)+j] = self.fArr[i][self.nPoly-j]*np.power(self.dt*(k+1), self.nPoly-j)
                observation[:,3+i*(self.nPoly+1)+self.nPoly] = observation[:,3+i*(self.nPoly+1)+self.nPoly-1] + self.fArr[i][0]
                pass
            pass
        return observation

    def observation2state(self, observation, vehId=None, tBeg=None, PrecInfo=None):
        # this is the function used for postprocessing and plotting
        # plotting ONLY!!!
        observation = observation.reshape(-1,self.nObservation)

        nStep = observation.shape[0]
        state = torch.zeros((nStep,self.nState))

        if PrecInfo is not None:
            dp = torch.FloatTensor(PrecInfo['d'])
            vp = torch.FloatTensor(PrecInfo['v'])
        else:
            # handle different k input
            k = observation[:,2].int()

            #dp, vp = self.getPrecedingVehicle(k, vehId, tBeg)
            k = torch.minimum(k, torch.FloatTensor([self.N])).int()
            dp = torch.FloatTensor(self.dp)[k]
            vp = torch.FloatTensor(self.vp)[k]

        if self.SELECT_OBSERVATION == 'state':         
            state[:,0]=observation[:,0]
            state[:,1]=observation[:,1]
        elif self.SELECT_OBSERVATION == 'diff':
            state[:,0]=dp-observation[:,0]
            state[:,1]=observation[:,1]
        elif self.SELECT_OBSERVATION == 'exp':
            state[:,0]=dp-observation[:,0]
            state[:,1]=observation[:,1]
        elif self.SELECT_OBSERVATION == 'test':
            state[:,0]=dp-observation[:,0]
            state[:,1]=observation[:,1]
        elif self.SELECT_OBSERVATION == 'poly':
            state[:,0]=dp-observation[:,0]
            state[:,1]=observation[:,1]
        elif self.SELECT_OBSERVATION == 'polylag':
            state[:,0]=dp-observation[:,0]
            state[:,1]=observation[:,1]

        return state

    def step(self, action):
        info = {}
        # clip action
        dmin = self.dlbFunc(self.vfinal)
        obs = self.observation.reshape((-1,self.nObservation))
        if len(obs[obs[:,0] < dmin,0]) > 0:
                action[obs[:,0] < dmin] = max(-0.5*(dmin-obs[obs[:,0] < dmin,0]),self.amin)

        state = self.state
        stateNext = self.getNextState(self.state, action)
        self.state = stateNext[0,:]

        reward = self.getReward(self.observation, action)
        obs = self.observation.reshape((-1,self.nObservation))
        df = obs[:,0]
        v = obs[:,1]
        k = obs[:,2]
        dftol = 1
        vftol = 1
        terminated = (self.dp[-1]-df>=self.df-dftol) & (self.dp[-1]-df<=self.df+dftol) & (v>=self.vf-vftol) & (v<=self.vf+vftol) & (k == self.N)
        truncated = (v < self.vmin) | (k == self.N)
 
        observationNext = self.calcDyn(self.observation, action, IS_OBS=True)

        self.k = self.k + 1
        #observationNext = self.state2Observation(self.state)

        self.observation = observationNext[0,:]

        return observationNext[0,:], reward[0], terminated[0], truncated[0]
  
    def sampleAction(self):
        action = torch.distributions.uniform.Uniform(self.amin, self.amax).sample([1]).reshape(-1,self.nAction)
        
        return action
    
    def replayEpisode(self, batch, PrecInfo=None):
        # PrecInfo: t, dp, vp

        observationBatch = torch.FloatTensor(batch[0])
        actionBatch = torch.FloatTensor(batch[2]).reshape(-1,self.nAction)

        if PrecInfo is None:
            PrecInfo = {'t': self.t,
                        'd': self.dp,
                        'v': self.vp}
        #     df_final = self.df_final
        #     vfinal = self.vfinal
        # else:
        df_final, vfinal = self.getDesiredFinalStates(observationBatch[-1,:].reshape(1,-1), observationBatch[-1,2])
        df_final = df_final.numpy()
        vfinal = vfinal.numpy()
            
        stateBatch = self.observation2state(observationBatch, PrecInfo=PrecInfo).cpu().data.numpy()
        
        #TrajDict = {'d':{'follow': PrecInfo['dp']-stateBatch[:,0], 'ubnd': np.hstack((self.dmax*np.ones(self.N),self.df_final)), 'lbnd': np.hstack((self.dmin*np.ones(self.N),self.df_final))},
                    # 'v': {'p_{}'.format(self.vehId): PrecInfo['vp'], 'opt': stateBatch[:,1], 'ubnd': np.hstack((self.vmax*np.ones(self.N),self.vfinal)), 'lbnd': np.hstack((self.vmin*np.ones(self.N),self.vfinal))}, 
                    # 'a': {'opt': batch[2]}}
        TrajDict = {'d':{'follow': PrecInfo['d']-stateBatch[:,0], 'ubnd': np.hstack((self.dmax*np.ones(len(PrecInfo['t'])-1),df_final)), 'lbnd': np.hstack((self.dlbFunc(PrecInfo['v'][:-1]),df_final))},
                    'v': {'p_{}'.format(self.vehId): PrecInfo['v'], 'opt': stateBatch[:,1], 'ubnd': np.hstack((self.vmax*np.ones(len(PrecInfo['t'])-1),vfinal)), 'lbnd': np.hstack((self.vmin*np.ones(len(PrecInfo['t'])-1),vfinal))}, 
                    'a': {'opt': batch[2]}}
        
        xaxis = PrecInfo['t']

        return xaxis, TrajDict
        
    
    def __dpFunc(self, k):
        Tdict = self.Utils_c.checkDtype(k)
 
        return Tdict['func']['interp1'](np.arange(self.N+1), self.dp.flatten(), k.flatten())
    
    def calcDiffOld(self, obs, act, obsnext, valueFunc, actorFunc):
        dynFunc = lambda observation, action: self.calcDyn(observation, action, IS_OBS=True)
        rFunc = lambda observation, action: self.getReward(observation, action, IS_OBS=True)
        pErr,uLoss,Info = self.Utils_c.calcDiffOld(obs, act, obsnext, valueFunc, actorFunc, dynFunc, rFunc, USE_CUDA=USE_CUDA)

        return pErr, uLoss, Info

    def calcDiff(self,  obs, act, obsnext, dAgent_dict, USE_CUDA=True):
        # used to do auto-differentiation
        pErr,uLoss,Info = self.Utils_c.calcDiff(obs, act, obsnext, dAgent_dict, self.dEnvDiff_dict, USE_CUDA=USE_CUDA)

        return pErr, uLoss, Info


    def __getBasisVal(self, fVal, k, i=0):
        Tdict = self.Utils_c.checkDtype(k)
        kCalc = Tdict['func']['clip'](k, i*self.nIntvlIdx, (i+1)*self.nIntvlIdx)
    
        basisVal = np.ones(kCalc.shape)*np.sum(fVal.reshape(-1,1)*np.array([(self.dt*(kCalc+1))**3, (self.dt*(kCalc+1))**2, (self.dt*(kCalc+1)), np.ones(kCalc.shape)]).reshape(len(fVal),-1))
        return basisVal
    
    def getDesiredFinalStates(self, obs, k):
        if self.SELECT_OBSERVATION == 'poly':     
            kCalc = k.reshape((-1,1)) # this is m-by-1 vector that used for calculation
            dpN = 0	# dp(N)
            dpN1 = 0 # dp(N-1)
            for j in range(self.nPoly+1):
                # skip linear term
                if j == self.nPoly-1:
                    continue
                dpN = dpN + obs[:,3+(self.nIntvl-1)*(self.nPoly+1)+j].reshape((-1,1))
                # if not last
                if j != self.nPoly:
                    dpN1 = dpN1 + obs[:,3+(self.nIntvl-1)*(self.nPoly+1)+j].reshape((-1,1))/(kCalc+1)**(self.nPoly-j)*(kCalc)**(self.nPoly-j)
                else:
                    dpN1 = dpN1 + obs[:,3+(self.nIntvl-1)*(self.nPoly+1)+j].reshape((-1,1))-(obs[:,3+(self.nIntvl-1)*(self.nPoly+1)+j-1].reshape((-1,1))/(kCalc+1))
        else:
            #vfinal = self.vp[-1]
            #vfinal = 15.08100945 #((self.dp[-1]-self.dp[-2])/self.dt)
            kCalc = k.reshape((-1,1)) # this is m-by-1 vector that used for calculation
            dpN = 0	# dp(N)
            dpN1 = 0 # dp(N-1)
            for j in range(self.nPoly+1):
                dpN = dpN + self.fArr[self.nIntvl-1][self.nPoly-j]*np.power(self.dt*(kCalc+1), self.nPoly-j)
                dpN1 = dpN1 + self.fArr[self.nIntvl-1][self.nPoly-j]*np.power(self.dt*(kCalc), self.nPoly-j)
            pass    

        #yvfinal = self.vp[-1]
        vfinal = ((dpN-dpN1)/self.dt)[:,0]    
        df_final = 1+2.5*vfinal
    
        return df_final, vfinal

    def getReward(self, xVar, action, IS_OBS=True):
        Tdict = self.Utils_c.checkDtype(xVar, action)

        action = action.reshape((-1,self.nAction))
        a = action[:,0]

        if not IS_OBS:
            xVar = xVar.reshape((-1,self.nState))
            d = xVar[:,0]
            v = xVar[:,1]     

            df = (self.dmin+self.dmax)/2
            k = 0
        else:        
            obs = xVar.reshape((-1,self.nObservation))

            df = obs[:,0]
            v = obs[:,1]
            k = obs[:,2]

        p1 = self.Veh['p1']
        p2 = self.Veh['p2']
        p3 = self.Veh['p3']

        # penalize k==self.N, which is the last state

        df_final, vfinal = self.getDesiredFinalStates(obs, k)
        vp = vfinal
        dmin = self.dlbFunc(vp)
        dfCalc = df #Tdict['func']['clip'](df, -10, 100)
        # if (p1*v+p2*(v**3)+p3*(v*a)) <0 :
        #     pow = 500
        # else:
        #     pow = (p1*v+p2*(v**3)+p3*(v*a))
        pow=Tdict['func']['clip']((p1*v+p2*(v**3)+p3*(v*a)),0,10e5)   
        reward =  -v*self.w1/(pow+500) +self.w2*(a**2) 
        # print("MPG:",-reward)
        # print("df_final ",df_final )
        
        # print("Clipped Power: ",Tdict['func']['sigmoid']((p1*v+p2*(v**3)+p3*(v*a)),0))
        # print("df_calc ",dfCalc)
        cf_max = Tdict['func']['sigmoid']((df - self.dmax),10)*((dfCalc - self.dmax)**2)
        cf_min = Tdict['func']['sigmoid']((dmin - df),10)*((dfCalc - dmin)**2)
        terminal =Tdict['func']['relu'](k-self.N+1)*(0.5*(dfCalc-df_final)**2+100*(v-vfinal))
        reward = reward + cf_max+ cf_min+terminal
       
        # print("Soft min following:",cf_min)
        # print("Soft max following:",cf_max)
        # print("Terminal Constrains:",terminal)
        reward = -reward/10**2
        # print("Final rewards",reward)
        if not IS_OBS:
            return reward
        
        if k.shape[0] == 1:
            self.df_final = df_final[-1]
            self.vfinal = vfinal[-1]
        return reward

    def calcDyn(self, xVar, action, IS_OBS=True):
        Tdict = self.Utils_c.checkDtype(xVar, action)
        action = action.reshape((-1,self.nAction))
        a = action[:,0].reshape((-1,1))
        if not IS_OBS:
            xVar = xVar.reshape((-1,self.nState))
            d = xVar[:,0].reshape((-1,1))
            v = xVar[:,1].reshape((-1,1))     

            dyn = Tdict['func']['hstack'](d+self.dt*v,
                                    Tdict['func']['clip'](v+self.dt*a, self.vmin, self.vmax))
        else:        
            obs = xVar.reshape((-1,self.nObservation))

            df = obs[:,0].reshape((-1,1))
            v = obs[:,1].reshape((-1,1))
            k = obs[:,2].reshape((-1,1))
            dyn = 0
            if self.SELECT_OBSERVATION == 'exp':      
                dpDelta = self.__dpFunc(k+1)-self.__dpFunc(k)
                dyn = Tdict['func']['hstack']((dpDelta+df-self.dt*v),
                                    Tdict['func']['clip'](v+self.dt*a, self.vmin, self.vmax),
                                    k+1)
            elif self.SELECT_OBSERVATION == 'poly':                
                def __dpFunc(obs, k):      
                    # use sigmoid to create lookup table based on k
                    dpCalc = 0
                    for i in range(self.nIntvl):
                        for j in range(self.nPoly+1):
                            # skip linear term
                            if j == self.nPoly-1:
                                continue
                            # if last interval
                            if i == self.nIntvl-1:
                                dpCalc = dpCalc + obs[:,3+i*(self.nPoly+1)+j].reshape((-1,1))*(Tdict['func']['sigmoid']((k+0.5-i*self.nIntvlIdx),20))
                            else:
                                dpCalc = dpCalc + obs[:,3+i*(self.nPoly+1)+j].reshape((-1,1))*(Tdict['func']['sigmoid']((k+0.5-i*self.nIntvlIdx),20)-Tdict['func']['sigmoid']((k+0.5-(i+1)*self.nIntvlIdx),20))
                    return dpCalc
                
                dpDelta = -__dpFunc(obs,k)
                dyn = Tdict['func']['hstack']((df-self.dt*v),
                                    Tdict['func']['clip'](v+self.dt*a, self.vmin, self.vmax),
                                    k+1)
                for i in range(self.nIntvl):
                    for j in range(self.nPoly+1):
                        # if not last
                        if j != self.nPoly:
                            dyn = Tdict['func']['hstack'](dyn,
                                        obs[:,3+i*(self.nPoly+1)+j].reshape((-1,1))*(k+2)**(self.nPoly-j)/(k+1)**(self.nPoly-j))
                        else:
                            dyn = Tdict['func']['hstack'](dyn,
                                        obs[:,3+i*(self.nPoly+1)+j].reshape((-1,1)) + obs[:,3+i*(self.nPoly+1)+j-1].reshape((-1,1))*((k+2)/(k+1)-1))
                dpDelta = dpDelta + __dpFunc(dyn, k+1)
                dyn[:,0:1] = (dpDelta+df-self.dt*v)
        
        return dyn