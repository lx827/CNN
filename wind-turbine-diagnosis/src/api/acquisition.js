import request from '../utils/request'

export const getAcquisitionAgents = () => request.get('/api/acquisition/agents')
export const getAcquisitionJobs = () => request.get('/api/acquisition/jobs')
export const createAcquisition = data => request.post('/api/acquisition/jobs', data)
export const getAcquisition = id => request.get(`/api/acquisition/jobs/${id}`)
export const stopAcquisition = id => request.post(`/api/acquisition/jobs/${id}/cancel`)
export const getAcquisitionAnalysis = id => request.get(`/api/acquisition/jobs/${id}/analysis`)
export const getAcquisitionWaveform = (id, params) => request.get(`/api/acquisition/jobs/${id}/waveform`, { params })

export const downloadAcquisitionFile = async (id, name) => {
  const blob = await request.get(`/api/acquisition/jobs/${id}/files/${name}`, { responseType: 'blob' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `${id}_${name}`
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
